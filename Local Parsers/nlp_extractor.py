# -*- coding: utf-8 -*-
import os
import sys
import json
import re
import datetime
import spacy
from bs4 import BeautifulSoup
from transformers import pipeline, AutoTokenizer, AutoModelForTokenClassification
import glob

# Load NLP models
try:
    print("Loading NLP models... (this may take a minute)")
    # Load spaCy for general NER
    nlp = spacy.load("en_core_web_lg")
    
    # Load Hugging Face transformers for specialized NER
    tokenizer = AutoTokenizer.from_pretrained("dslim/bert-base-NER")
    model = AutoModelForTokenClassification.from_pretrained("dslim/bert-base-NER")
    ner_pipeline = pipeline("ner", model=model, tokenizer=tokenizer, aggregation_strategy="simple")
    
    # Zero-shot classification for crime categorization
    classifier = pipeline("zero-shot-classification", 
                         model="facebook/bart-large-mnli",
                         device=-1)  # Use CPU
    
    models_loaded = True
    print("Models loaded successfully!")
except Exception as e:
    print(f"Could not load all models: {str(e)}")
    models_loaded = False

# [All helper functions and extraction functions remain the same as in the previous script]
# Helper functions
def clean_text(text):
    """Clean text by removing extra whitespace and normalizing quotes."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('"', '"').replace('"', '"')
    return text.strip()

def text_to_chunks(text, max_length=512, overlap=50):
    """Split text into overlapping chunks."""
    words = text.split()
    chunks = []
    
    if len(words) <= max_length:
        return [text]
    
    i = 0
    while i < len(words):
        chunk = ' '.join(words[i:i + max_length])
        chunks.append(chunk)
        i += max_length - overlap
    
    return chunks

# Content extraction functions
def extract_content_from_html(html_path):
    """Extract content from HTML using multiple fallback strategies."""
    try:
        with open(html_path, 'r', encoding='utf-8') as file:
            content = file.read()
    except UnicodeDecodeError:
        # Try another encoding if UTF-8 fails
        with open(html_path, 'r', encoding='latin-1') as file:
            content = file.read()
    
    # Strategy 1: Look for JSON content in the HTML
    try:
        json_match = re.search(r'(\{[\s\S]*"title"[\s\S]*"content"[\s\S]*\})', content)
        if json_match:
            data = json.loads(json_match.group(1))
            if data.get("content") and len(data.get("content", "")) > 100:
                return {
                    "title": data.get("title", ""),
                    "content": data.get("content", ""),
                    "html_path": html_path,
                    "extraction_method": "json_in_html"
                }
    except:
        pass
    
    # Strategy 2: Try parsing as pure JSON
    if content.strip().startswith('{') and content.strip().endswith('}'):
        try:
            data = json.loads(content)
            if data.get("content") and len(data.get("content", "")) > 100:
                return {
                    "title": data.get("title", ""),
                    "content": data.get("content", ""),
                    "html_path": html_path,
                    "extraction_method": "pure_json"
                }
        except:
            pass
    
    # Strategy 3: Parse with BeautifulSoup
    soup = BeautifulSoup(content, 'html.parser')
    
    # Try multiple title selectors
    title = ""
    title_selectors = [
        'h1', '.uk-article-title', '.page-header h1', '.title', 
        'title', 'article h1', '.article-title'
    ]
    
    for selector in title_selectors:
        elements = soup.select(selector)
        if elements:
            title = elements[0].text.strip()
            if len(title) > 5 and title != "News":
                break
    
    # Try multiple content selectors
    article_content = ""
    content_selectors = [
        'article p', '.uk-article p', '.tm-main p', '.article-body p',
        '.item-page p', '.content p', 'main p', '.entry-content p'
    ]
    
    for selector in content_selectors:
        elements = soup.select(selector)
        if elements and len(elements) > 1:  # At least 2 paragraphs
            paragraphs = [p.text.strip() for p in elements if p.text.strip()]
            if paragraphs:
                article_content = "\n\n".join(paragraphs)
                if len(article_content) > 200:  # More than 200 chars
                    break
    
    # Fallback: Get all paragraphs
    if not article_content or len(article_content) < 200:
        paragraphs = [p.text.strip() for p in soup.find_all('p') if p.text.strip() and len(p.text.strip()) > 20]
        if paragraphs:
            article_content = "\n\n".join(paragraphs)
    
    # Last resort: Extract from raw text
    if not article_content or len(article_content) < 200:
        raw_text = soup.get_text(separator='\n\n')
        # Remove very short lines and excessive whitespace
        lines = [line.strip() for line in raw_text.split('\n') if len(line.strip()) > 20]
        article_content = '\n\n'.join(lines)
    
    return {
        "title": title,
        "content": article_content,
        "html_path": html_path,
        "extraction_method": "html_parsing"
    }

# Entity extraction functions
def extract_entities_spacy(text):
    """Extract entities using spaCy."""
    if not text or not models_loaded:
        return {
            "people": [],
            "locations": [],
            "organizations": [],
            "dates": []
        }
    
    doc = nlp(text)
    
    entities = {
        "people": [],
        "locations": [],
        "organizations": [],
        "dates": []
    }
    
    for ent in doc.ents:
        if ent.label_ == "PERSON":
            entities["people"].append(ent.text)
        elif ent.label_ in ["GPE", "LOC"]:
            entities["locations"].append(ent.text)
        elif ent.label_ == "ORG":
            entities["organizations"].append(ent.text)
        elif ent.label_ in ["DATE", "TIME"]:
            entities["dates"].append(ent.text)
    
    # Remove duplicates
    for key in entities:
        entities[key] = list(set(entities[key]))
    
    return entities

def extract_entities_transformers(text, chunk_size=512):
    """Extract entities using Hugging Face transformers."""
    if not text or not models_loaded:
        return []
    
    # Split text into chunks to avoid token limits
    chunks = text_to_chunks(text, chunk_size, overlap=50)
    
    all_entities = []
    for chunk in chunks:
        try:
            entities = ner_pipeline(chunk)
            all_entities.extend(entities)
        except Exception as e:
            print(f"Error in transformers NER: {str(e)}")
    
    return all_entities

def categorize_crime(text):
    """Categorize crime types using zero-shot classification."""
    if not text or not models_loaded:
        return []
    
    crime_categories = [
        "Drug Trafficking", 
        "Money Laundering", 
        "Firearms Offenses", 
        "Fraud",
        "People Smuggling",
        "Child Sexual Abuse",
        "Cybercrime",
        "Organized Crime",
        "Violent Crime",
        "Terrorism"
    ]
    
    try:
        # Use shorter text for classification to stay within token limits
        classification = classifier(
            text[:2000], 
            candidate_labels=crime_categories,
            multi_label=True
        )
        
        results = []
        for i, label in enumerate(classification['labels']):
            score = classification['scores'][i]
            if score > 0.3:  # Only include if confidence is > 30%
                results.append({
                    "category": label,
                    "confidence": score
                })
        
        return results
    except Exception as e:
        print(f"Error in crime categorization: {str(e)}")
        return []

# Extraction of structured data
def extract_perpetrators(text, people):
    """Extract perpetrators with details using context patterns."""
    perpetrators = []
    
    # Common crime-related words to look for near names
    crime_indicators = [
        'convicted', 'sentenced', 'pleaded guilty', 'admitted', 'arrested', 
        'charged', 'jailed', 'imprisoned', 'smuggler', 'dealer', 'trafficker'
    ]
    
    # Process each person
    for person in people:
        person = person.strip()
        if len(person) < 4 or person.lower() in ['he', 'she', 'they', 'him', 'her']:
            continue
        
        # Create windows around the person's name
        name_positions = [m.start() for m in re.finditer(re.escape(person), text)]
        is_perpetrator = False
        age = ""
        location = ""
        
        for pos in name_positions:
            # Look at a window of text around the name
            window_start = max(0, pos - 200)
            window_end = min(len(text), pos + 200)
            window = text[window_start:window_end]
            
            # Check if any crime indicators are in the window
            for indicator in crime_indicators:
                if indicator in window.lower():
                    is_perpetrator = True
                    break
            
            # If this is a perpetrator, extract age and location
            if is_perpetrator:
                # Extract age - common patterns
                age_patterns = [
                    r'\b' + re.escape(person) + r'.*?(\d{1,2})[,\s]',
                    r'\b' + re.escape(person) + r'.*?aged\s+(\d{1,2})',
                    r'(\d{1,2})[\-\s]year[\-\s]old\s+' + re.escape(person)
                ]
                
                for pattern in age_patterns:
                    age_match = re.search(pattern, window)
                    if age_match:
                        age = age_match.group(1)
                        break
                
                # Extract location - common patterns
                location_patterns = [
                    r'\b' + re.escape(person) + r'.*?from\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                    r'\b' + re.escape(person) + r'.*?of\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
                    r'\b' + re.escape(person) + r'.*?in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
                ]
                
                for pattern in location_patterns:
                    location_match = re.search(pattern, window)
                    if location_match:
                        location = location_match.group(1)
                        break
            
            if is_perpetrator:
                break
        
        if is_perpetrator:
            perpetrator = {
                "name": person,
                "age": age,
                "location": location
            }
            
            # Check if we already have this person
            if not any(p["name"] == person for p in perpetrators):
                perpetrators.append(perpetrator)
    
    return perpetrators

def extract_sentences(text):
    """Extract prison sentences using regex patterns."""
    sentence_patterns = [
        r'sentenced to\s+([^\.;]+)',
        r'jailed for\s+([^\.;]+)',
        r'imprisonment of\s+([^\.;]+)',
        r'([^\.;]+?)\s+imprisonment',
        r'sentenced\s+([^\.;]+?)\s+to\s+([^\.;]+)'
    ]
    
    sentences = []
    for pattern in sentence_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            sentence = match.group(1).strip()
            # Filter for likely sentence text
            if any(word in sentence.lower() for word in ['year', 'month', 'week']) and re.search(r'\d+', sentence):
                if not any(sentence in s for s in sentences):
                    sentences.append(sentence)
    
    return sentences

def extract_charges(text):
    """Extract criminal charges."""
    charge_patterns = [
        r'(?:pleaded guilty to|admitted|convicted of|charged with)\s+([^\.;]+)',
        r'(?:charges of|accused of|committed)\s+([^\.;]+)',
        r'(?:found guilty of|in connection with)\s+([^\.;]+)'
    ]
    
    charges = []
    for pattern in charge_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            charge = match.group(1).strip()
            if charge and not any(charge in c for c in charges):
                charges.append(charge)
    
    return charges

def extract_money_amounts(text):
    """Extract monetary amounts."""
    money_pattern = r'\u00A3\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(million|billion|m|k|thousand)?'
    money_amounts = []
    
    for match in re.finditer(money_pattern, text):
        amount = match.group(1).replace(',', '')
        unit = match.group(2) or ''
        
        # Convert to numerical value
        numerical_amount = float(amount)
        if unit.lower() in ['million', 'm']:
            numerical_amount *= 1000000
        elif unit.lower() == 'billion':
            numerical_amount *= 1000000000
        elif unit.lower() in ['k', 'thousand']:
            numerical_amount *= 1000
        
        money_amounts.append({
            "original": match.group(0),
            "amount": numerical_amount,
            "formatted": f"\u00A3{numerical_amount:,.0f}"
        })
    
    return money_amounts

def extract_drug_quantities(text):
    """Extract drug quantities."""
    drug_pattern = r'(\d+(?:\.\d+)?)\s*(tons?|kilos?|kg|grams?|g|tonnes?)\s+(?:of\s+)?(cocaine|heroin|cannabis|mdma|drugs)'
    drug_quantities = []
    
    for match in re.finditer(drug_pattern, text, re.IGNORECASE):
        quantity = float(match.group(1))
        unit = match.group(2).lower()
        drug_type = match.group(3).lower()
        
        # Normalize to kg
        kg_equivalent = quantity
        if 'ton' in unit or 'tonne' in unit:
            kg_equivalent = quantity * 1000
        elif unit.startswith('g') and not 'kg' in unit:
            kg_equivalent = quantity / 1000
        
        drug_quantities.append({
            "original": match.group(0),
            "quantity": quantity,
            "unit": unit,
            "drug": drug_type,
            "kgEquivalent": kg_equivalent
        })
    
    return drug_quantities

def extract_timeline(text, dates):
    """Extract timeline events using NER dates and regex."""
    timeline = []
    
    # Add dates from NER
    for date in dates:
        if re.search(r'\d{4}', date):  # Must include a year
            timeline.append(date)
    
    # Also look for specific date patterns
    date_patterns = [
        r'(\d{1,2}(?:st|nd|rd|th)?\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})',
        r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,\s+\d{4})'
    ]
    
    for pattern in date_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            date = match.group(1)
            if date not in timeline:
                timeline.append(date)
    
    return timeline

# Main extraction function
def process_article(file_path):
    """Process an article file and extract structured data."""
    # Extract the content
    article_data = extract_content_from_html(file_path)
    title = article_data["title"]
    content = article_data["content"]
    
    # Skip if no meaningful content
    if not content or len(content) < 100:
        print(f"Error: Could not extract content from {file_path}")
        return {
            "title": title,
            "content": content,
            "source": os.path.basename(file_path),
            "processedAt": datetime.datetime.now().isoformat(),
            "extraction_error": "Insufficient content extracted"
        }
    
    # Entity extraction using spaCy
    spacy_entities = extract_entities_spacy(content)
    
    # Extract perpetrators
    perpetrators = extract_perpetrators(content, spacy_entities["people"])
    
    # Extract sentences, charges, money, drugs
    sentences = extract_sentences(content)
    charges = extract_charges(content)
    money_amounts = extract_money_amounts(content)
    drug_quantities = extract_drug_quantities(content)
    
    # Extract timeline
    timeline = extract_timeline(content, spacy_entities["dates"])
    
    # Crime categorization
    crime_categories = categorize_crime(content) if models_loaded else []
    
    # Compile and return the results
    result = {
        "title": title,
        "content": content,
        "source": os.path.basename(file_path),
        "processedAt": datetime.datetime.now().isoformat(),
        "locations": spacy_entities["locations"],
        "organizations": spacy_entities["organizations"],
        "timeline": timeline,
        "perpetrators": perpetrators,
        "sentences": sentences,
        "charges": charges,
        "moneyAmounts": money_amounts,
        "drugQuantities": drug_quantities,
        "categories": [c["category"] for c in crime_categories if c["confidence"] > 0.4]
    }
    
    return result

# Process a folder of HTML files
def process_folder(folder_path, output_file=None):
    """Process all HTML files in a folder and save results to a JSON file."""
    if not os.path.isdir(folder_path):
        print(f"Error: {folder_path} is not a valid directory")
        return
    
    # Get all HTML files in the folder
    html_files = glob.glob(os.path.join(folder_path, "*.html"))
    
    if not html_files:
        print(f"No HTML files found in {folder_path}")
        return
    
    # Process each file
    results = []
    total_files = len(html_files)
    print(f"Found {total_files} HTML files to process")
    
    for i, file_path in enumerate(html_files):
        print(f"Processing file {i+1}/{total_files}: {os.path.basename(file_path)}")
        try:
            result = process_article(file_path)
            results.append(result)
            print(f"  Successfully processed: {os.path.basename(file_path)}")
        except Exception as e:
            print(f"  Error processing {os.path.basename(file_path)}: {str(e)}")
            results.append({
                "error": str(e),
                "source": os.path.basename(file_path),
                "processedAt": datetime.datetime.now().isoformat()
            })
    
    # Save results to a JSON file if output_file is specified
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Results saved to {output_file}")
    
    return results

# Main execution
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python nlp_extractor.py <html_file_or_folder> [output_file]")
        sys.exit(1)
    
    path = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    
    if os.path.isdir(path):
        # Process all HTML files in the folder
        results = process_folder(path, output_file)
        if not output_file:
            # Print the results as JSON if no output file is specified
            print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        # Process a single file
        try:
            result = process_article(path)
            # Print the result as JSON
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
            # Save to output file if specified
            if output_file:
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                print(f"Result saved to {output_file}")
        except Exception as e:
            print(json.dumps({
                "error": str(e),
                "source": os.path.basename(path),
                "processedAt": datetime.datetime.now().isoformat()
            }, indent=2, ensure_ascii=False))