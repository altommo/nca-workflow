# -*- coding: utf-8 -*-
import os
import sys
import json
import re
import datetime
from bs4 import BeautifulSoup
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline, AutoModelForSequenceClassification

# Define the basic information
SCRIPT_VERSION = "1.0.0"
DESCRIPTION = "BERT-based article analyzer for NCA workflow"

# Helper functions
def clean_text(text):
    """Clean text by removing extra whitespace and normalizing quotes."""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    text = text.replace('"', '"').replace('"', '"')
    return text.strip()

def text_to_chunks(text, max_length=512, overlap=50):
    """Split text into overlapping chunks to handle BERT token limits."""
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

def extract_content_from_html(html_path):
    """Extract content from HTML file."""
    try:
        with open(html_path, 'r', encoding='utf-8') as file:
            content = file.read()
    except UnicodeDecodeError:
        # Try another encoding if UTF-8 fails
        with open(html_path, 'r', encoding='latin-1') as file:
            content = file.read()
    
    # Strategy 1: Look for JSON content in the HTML
    try:
        json_match = re.search(r'(\{[\s\S]*\"title\"[\s\S]*\"content\"[\s\S]*\})', content)
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
    
    # Strategy 2: Parse with BeautifulSoup
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
    
    return {
        "title": title,
        "content": article_content,
        "html_path": html_path,
        "extraction_method": "html_parsing"
    }

# BERT-specific functions
class BERTProcessor:
    def __init__(self, model_name="google-bert/bert-base-cased"):
        print(f"Initializing BERT Processor with model: {model_name}")
        
        # Initialize tokenizer and NER model
        self.ner_tokenizer = AutoTokenizer.from_pretrained("dslim/bert-base-NER")
        self.ner_model = AutoModelForTokenClassification.from_pretrained("dslim/bert-base-NER")
        self.ner_pipeline = pipeline("ner", model=self.ner_model, tokenizer=self.ner_tokenizer, aggregation_strategy="simple")
        
        # Initialize classification model
        self.cls_tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.cls_model = AutoModelForSequenceClassification.from_pretrained(model_name, num_labels=7)
        self.cls_pipeline = pipeline("text-classification", model=self.cls_model, tokenizer=self.cls_tokenizer)
        
        # Define crime categories for classification
        self.crime_categories = [
            "Drug Trafficking", 
            "Money Laundering", 
            "Firearms Offenses", 
            "Fraud",
            "Human Trafficking",
            "Cybercrime",
            "Terrorism"
        ]
        
        print("BERT models loaded successfully")
    
    def extract_named_entities(self, text):
        """Extract named entities using BERT NER."""
        if not text:
            return []
        
        # Split into chunks to handle token limits
        chunks = text_to_chunks(text)
        all_entities = []
        
        for chunk in chunks:
            try:
                entities = self.ner_pipeline(chunk)
                all_entities.extend(entities)
            except Exception as e:
                print(f"Error in BERT NER: {str(e)}")
        
        # Organize entities by type
        organized_entities = {
            "people": [],
            "locations": [],
            "organizations": [],
            "miscellaneous": []
        }
        
        for entity in all_entities:
            entity_text = entity.get("word", "").strip()
            entity_type = entity.get("entity_group", "").strip()
            
            if entity_text and len(entity_text) > 1:
                if entity_type == "PER":
                    organized_entities["people"].append(entity_text)
                elif entity_type == "LOC":
                    organized_entities["locations"].append(entity_text)
                elif entity_type == "ORG":
                    organized_entities["organizations"].append(entity_text)
                else:
                    organized_entities["miscellaneous"].append(entity_text)
        
        # Remove duplicates
        for category in organized_entities:
            organized_entities[category] = list(set(organized_entities[category]))
        
        return organized_entities
    
    def classify_text(self, text, threshold=0.3):
        """Classify text into predefined categories."""
        if not text:
            return []
        
        # Prepare text for classification (truncate if needed)
        short_text = text[:500]  # Use shorter text to stay within token limits
        
        try:
            # Custom classification for crime categories
            results = []
            for category in self.crime_categories:
                # For each category, check if the text contains relevant keywords
                category_keywords = self._get_keywords_for_category(category)
                score = 0
                
                # Simple keyword matching for classification
                for keyword in category_keywords:
                    if keyword.lower() in text.lower():
                        score += 0.2  # Increase score for each matched keyword
                
                if score > threshold:
                    results.append({
                        "category": category,
                        "confidence": min(score, 0.95)  # Cap at 0.95
                    })
            
            return results
            
        except Exception as e:
            print(f"Error in BERT classification: {str(e)}")
            return []
    
    def _get_keywords_for_category(self, category):
        """Get keywords for a specific crime category."""
        keywords = {
            "Drug Trafficking": ["drug", "cocaine", "heroin", "cannabis", "trafficking", "smuggling", "narcotics"],
            "Money Laundering": ["money laundering", "financial crime", "illegal proceeds", "cash", "offshore", "bank account"],
            "Firearms Offenses": ["firearm", "gun", "weapon", "ammunition", "pistol", "rifle", "shotgun"],
            "Fraud": ["fraud", "scam", "defraud", "counterfeit", "fake", "victim", "scheme"],
            "Human Trafficking": ["trafficking", "smuggling", "migrant", "illegal entry", "immigration", "border"],
            "Cybercrime": ["cyber", "online", "internet", "hacker", "ransomware", "malware", "computer"],
            "Terrorism": ["terror", "extremist", "attack", "bomb", "explosive", "threat", "security"]
        }
        
        return keywords.get(category, [])
    
    def extract_relationships(self, text, entities):
        """Extract relationships between entities."""
        relationships = []
        
        # Get people and organizations
        people = entities.get("people", [])
        organizations = entities.get("organizations", [])
        
        # Look for relationships between people and organizations
        for person in people:
            for org in organizations:
                # Create windows around the person's name
                person_positions = [m.start() for m in re.finditer(re.escape(person), text)]
                
                for pos in person_positions:
                    # Define a window around the person mention
                    window_start = max(0, pos - 100)
                    window_end = min(len(text), pos + 100)
                    window = text[window_start:window_end]
                    
                    # Check if organization is mentioned within this window
                    if org in window:
                        # Look for relationship indicators
                        for indicator in ["member of", "works for", "associated with", "leader of", "part of"]:
                            if indicator in window.lower():
                                relationships.append({
                                    "from": person,
                                    "to": org,
                                    "relationship": indicator
                                })
                                break
        
        return relationships
    
    def extract_key_quotes(self, text):
        """Extract important quotes from the text."""
        quotes = []
        
        # Find quoted text
        quote_matches = re.finditer(r'"([^"]+)"', text)
        for match in quote_matches:
            quote = match.group(1).strip()
            if len(quote) > 20:  # Only include meaningful quotes
                quotes.append(quote)
        
        return quotes[:5]  # Limit to top 5 quotes
    
    def summarize(self, text, max_length=200):
        """Generate a short summary of the article."""
        if len(text) <= max_length:
            return text
        
        # Extract the first few sentences for a basic summary
        sentences = re.split(r'(?<=[.!?])\s+', text)
        summary = ""
        
        for sentence in sentences:
            if len(summary) + len(sentence) <= max_length:
                summary += sentence + " "
            else:
                break
        
        return summary.strip()

# Main processing function
def process_article(file_path, bert_processor):
    """Process an article and extract structured information using BERT."""
    # Extract content from HTML
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
    
    # Extract named entities
    entities = bert_processor.extract_named_entities(content)
    
    # Classify text into categories
    categories = bert_processor.classify_text(content)
    
    # Extract relationships between entities
    relationships = bert_processor.extract_relationships(content, entities)
    
    # Extract key quotes
    quotes = bert_processor.extract_key_quotes(content)
    
    # Generate summary
    summary = bert_processor.summarize(content)
    
    # Compile and return results
    result = {
        "title": title,
        "content": content,
        "summary": summary,
        "source": os.path.basename(file_path),
        "processedAt": datetime.datetime.now().isoformat(),
        "entities": entities,
        "categories": [c["category"] for c in categories if c["confidence"] > 0.3],
        "relationships": relationships,
        "quotes": quotes
    }
    
    return result

# Process multiple files
def process_folder(folder_path, output_file=None, model_name="google-bert/bert-base-cased"):
    """Process all HTML files in a folder."""
    if not os.path.isdir(folder_path):
        print(f"Error: {folder_path} is not a valid directory")
        return
    
    # Initialize BERT processor
    bert_processor = BERTProcessor(model_name)
    
    # Get all HTML files in the folder
    html_files = []
    for file in os.listdir(folder_path):
        if file.endswith(".html"):
            html_files.append(os.path.join(folder_path, file))
    
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
            result = process_article(file_path, bert_processor)
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
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Results saved to {output_file}")
    
    return results

# Main execution
if __name__ == "__main__":
    print(f"BERT Article Analyzer v{SCRIPT_VERSION}")
    print(f"Description: {DESCRIPTION}")
    
    if len(sys.argv) < 2:
        print("Usage: python bert_article_analyzer.py <html_file_or_folder> [output_file] [model_name]")
        sys.exit(1)
    
    path = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None
    model_name = sys.argv[3] if len(sys.argv) > 3 else "google-bert/bert-base-cased"
    
    print(f"Using model: {model_name}")
    
    if os.path.isdir(path):
        # Process all HTML files in the folder
        results = process_folder(path, output_file, model_name)
        if not output_file:
            # Print the results as JSON if no output file is specified
            print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        # Process a single file
        try:
            # Initialize BERT processor
            bert_processor = BERTProcessor(model_name)
            
            # Process the article
            result = process_article(path, bert_processor)
            
            # Print the result as JSON
            print(json.dumps(result, indent=2, ensure_ascii=False))
            
            # Save to output file if specified
            if output_file:
                os.makedirs(os.path.dirname(output_file), exist_ok=True)
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, indent=2, ensure_ascii=False)
                print(f"Result saved to {output_file}")
        except Exception as e:
            print(json.dumps({
                "error": str(e),
                "source": os.path.basename(path),
                "processedAt": datetime.datetime.now().isoformat()
            }, indent=2, ensure_ascii=False))
