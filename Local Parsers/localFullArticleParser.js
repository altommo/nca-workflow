#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const cheerio = require('cheerio');

// Constants for entity recognition
const UK_LOCATIONS = [
    'London', 'Manchester', 'Birmingham', 'Leeds', 'Liverpool', 'Glasgow', 'Edinburgh',
    'Bristol', 'Sheffield', 'Newcastle', 'Nottingham', 'Cardiff', 'Belfast', 'Derby',
    'Leicester', 'Southampton', 'Portsmouth', 'Brighton', 'Plymouth', 'Aberdeen',
    'Greater London', 'West Midlands', 'Greater Manchester', 'West Yorkshire',
    'South Yorkshire', 'West Country', 'East Anglia', 'Home Counties',
    'Kent', 'Surrey', 'Essex', 'Hampshire', 'Devon', 'Lancashire', 'Cheshire',
    'UK', 'England', 'Scotland', 'Wales', 'Northern Ireland', 'Republic of Ireland',
    'Dover', 'Hull', 'Leicester', 'Bradford', 'Rotherham', 'Sunderland', 'Bolton',
    'West London', 'East London', 'North London', 'South London', 'Midlands',
    'Yorkshire', 'Merseyside', 'Teesside', 'Tyneside', 'Heathrow', 'Gatwick'
];

const LAW_ENFORCEMENT_ORGS = [
    'National Crime Agency', 'NCA', 'Metropolitan Police', 'Met Police', 'Police Scotland',
    'City of London Police', 'British Transport Police', 'Border Force', 'HM Revenue & Customs',
    'Crown Prosecution Service', 'CPS', 'National Police Chiefs Council', 'Interpol', 'Europol',
    'Organised Crime Partnership', 'OCP', 'Armed Operations Unit', 'Home Office Immigration Enforcement',
    'Cleveland Police', 'West Midlands Police', 'Derbyshire Police', 'Metropolitan Police', 'HMRC'
];

const VICTIM_KEYWORDS = new Set([
    'victim', 'victims', 'targeted', 'assaulted', 'injured', 'killed', 'murdered',
    'exploited', 'abused', 'harmed', 'attacked', 'affected', 'vulnerable', 'survivor',
    'survivors', 'child victims', 'sexually exploited', 'trafficked', 'missing person',
    'migrants', 'minor', 'minors', 'young girl', 'young boy', 'children'
]);

const PERP_KEYWORDS = new Set([
    'arrested', 'charged', 'convicted', 'sentenced', 'pleaded', 'admitted', 'defendant',
    'accused', 'suspect', 'perpetrator', 'offender', 'gang member', 'conspirator',
    'smuggler', 'trafficker', 'dealer', 'criminal', 'ringleader', 'mastermind', 'fugitive'
]);

// Category mapping
const CATEGORY_KEYWORDS = {
    'Drug trafficking': ['drug', 'cocaine', 'heroin', 'cannabis', 'ketamine', 'amphetamine', 'class A', 'narcotic'],
    'Firearms': ['gun', 'firearm', 'pistol', 'weapon', 'ammunition', 'shotgun', 'rifle'],
    'Money laundering': ['money laundering', 'launder', 'cash', 'financial', 'proceeds of crime'],
    'People smuggling': ['smuggling', 'small boat', 'migrant', 'channel crossing', 'immigration'],
    'Human trafficking': ['trafficking', 'modern slavery', 'forced labor', 'exploitation'],
    'Child sexual abuse': ['child', 'sexual abuse', 'indecent', 'sexual exploitation'],
    'Cyber crime': ['cyber', 'online', 'internet', 'dark web', 'hack', 'ransomware'],
    'Organized crime': ['organised crime', 'organized crime', 'criminal group', 'gang', 'network'],
    'Fraud': ['fraud', 'scam', 'counterfeit', 'fake', 'forgery']
};

// Main processing function
function processFolder(inputFolder, outputFolder) {
    try {
        const htmlFiles = getHtmlFiles(inputFolder);
        const reports = [];

        htmlFiles.forEach(filePath => {
            try {
                const html = fs.readFileSync(filePath, 'utf8');
                const $ = cheerio.load(html);
                const title = extractTitle($);
                const content = extractContent($);
                
                // Initialize structured data
                const locations = extractLocations(content);
                const organizations = extractOrganizations(content);
                const timeline = extractTimeline(content, $);
                const perpetrators = extractPeople(content, 'perpetrator');
                const victims = extractPeople(content, 'victim');
                const sentences = extractSentences(content);
                const charges = extractCharges(content);
                const financials = extractFinancials(content);
                const drugs = extractDrugQuantities(content);
                
                // Create article URL from title
                const url = createUrlFromTitle(title);
                
                // Extract intro paragraph
                const intro = extractIntro($, content);
                
                // Extract or guess date
                const date = extractDate(content, $);
                
                // Extract image URL
                const imageUrl = extractMainImage($);
                
                // Determine categories
                const categories = determineCategories(content, title);
                
                const report = {
                    title: title,
                    content: content,
                    source: path.basename(filePath),
                    processedAt: new Date().toISOString(),
                    locations: locations,
                    organizations: organizations,
                    timeline: timeline,
                    perpetrators: perpetrators.map(p => p.name),
                    sentences: sentences,
                    charges: charges,
                    moneyAmounts: financials.map(f => ({
                        original: f.originalText,
                        amount: f.amount,
                        formatted: formatCurrency(f.amount)
                    })),
                    drugQuantities: drugs.map(d => ({
                        original: `${d.quantity} ${d.unit} of ${d.substance}`,
                        quantity: d.quantity,
                        unit: d.unit,
                        drug: d.substance,
                        kgEquivalent: convertToKg(d.quantity, d.unit)
                    })),
                    categories: categories,
                    url: url,
                    intro: intro,
                    date: date,
                    imageUrl: imageUrl
                };

                reports.push(report);
            } catch (fileError) {
                console.error(`Error processing ${filePath}: ${fileError.message}`);
            }
        });

        saveReports(reports, path.join(outputFolder, 'report.json'));
        console.log(`Processed ${reports.length} files. Output saved to ${path.join(outputFolder, 'report.json')}`);
        
        // Output to console for n8n to capture
        console.log(JSON.stringify(reports, null, 2));

    } catch (error) {
        console.error('Processing failed:', error.message);
        process.exit(1);
    }
}

// Function to convert drug quantities to kg
function convertToKg(quantity, unit) {
    const unitLower = unit.toLowerCase();
    if (unitLower.includes('kg') || unitLower.includes('kilo')) {
        return quantity;
    } else if (unitLower.includes('gram')) {
        return quantity / 1000;
    } else if (unitLower.includes('tonne')) {
        return quantity * 1000;
    } else if (unitLower.includes('lb') || unitLower.includes('pound')) {
        return quantity * 0.453592;
    }
    return quantity; // default if unit is unknown
}

// Function to format currency
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-GB', { 
        style: 'currency', 
        currency: 'GBP',
        maximumFractionDigits: 0
    }).format(amount);
}

// Create URL from title
function createUrlFromTitle(title) {
    if (!title) return '';
    
    const baseUrl = 'https://www.nationalcrimeagency.gov.uk/news/';
    const slug = title
        .toLowerCase()
        .replace(/[^\w\s-]/g, '') // Remove special characters
        .replace(/\s+/g, '-')     // Replace spaces with hyphens
        .replace(/-+/g, '-');     // Replace multiple hyphens with single hyphen
    
    return baseUrl + slug;
}

// Helper functions
function getHtmlFiles(folderPath) {
    const items = fs.readdirSync(folderPath);
    return items
        .map(item => path.join(folderPath, item))
        .filter(itemPath => {
            const stats = fs.statSync(itemPath);
            return stats.isFile() && path.extname(itemPath).toLowerCase() === '.html';
        });
}

function extractTitle($) {
    const selectors = [
        'h1.uk-article-title', 
        'h1.page-header', 
        'article h1', 
        'meta[property="og:title"]',
        'title'
    ];
    
    for (const selector of selectors) {
        const el = $(selector).first();
        if (el.length) {
            const title = el.attr('content') || el.text().trim();
            if (title && title !== 'News') {
                return title.replace(' - National Crime Agency', '');
            }
        }
    }
    return 'No title found';
}
function extractContent($) {
    // Try multiple selector approaches to get the most complete content
    let paragraphs = [];
    
    // First approach: Standard article selectors
    const standardSelectors = [
        'article p', 
        '.uk-article p', 
        '.tm-main p',
        '.article-body p',
        '.content-area p',
        '.entry-content p',
        '.main-content p'
    ];
    
    // Try each selector and use the one that gives the most content
    for (const selector of standardSelectors) {
        const selected = $(selector)
            .map((i, el) => $(el).text().trim())
            .get()
            .filter(text => text.length > 0);
            
        if (selected.length > paragraphs.length) {
            paragraphs = selected;
        }
    }
    
    // If we still have no content, try a more aggressive approach
    if (paragraphs.length === 0) {
        // Try to find the most likely content container
        const mainContainers = [
            'article', 
            '.article', 
            '.post', 
            '.entry', 
            'main', 
            '.content',
            '#content',
            '.main-content',
            '.article-content'
        ];
        
        for (const container of mainContainers) {
            if ($(container).length) {
                // Found a container, extract all paragraphs from it
                paragraphs = $(container)
                    .find('p')
                    .map((i, el) => $(el).text().trim())
                    .get()
                    .filter(text => text.length > 0);
                    
                if (paragraphs.length > 0) {
                    break;
                }
            }
        }
    }
    
    // Last resort: get all paragraphs from the document
    if (paragraphs.length === 0) {
        paragraphs = $('p')
            .map((i, el) => $(el).text().trim())
            .get()
            .filter(text => text.length > 0);
    }
    
    // Join the paragraphs with double newlines
    return paragraphs.join('\n\n');
}

function extractIntro($, content) {
    // Try to find the intro paragraph
    const firstPara = $('article p, .uk-article p, .tm-main p').first().text().trim();
    if (firstPara && firstPara.length > 20 && firstPara.length < 300) {
        return firstPara;
    }
    
    // If we can't find a good paragraph, use the first few sentences of content
    if (content) {
        const sentences = content.split(/\.\s+/);
        if (sentences.length > 0) {
            return sentences[0] + (sentences.length > 1 ? '. ' + sentences[1] : '');
        }
    }
    
    return '';
}

function extractMainImage($) {
    // Look for the main image with various selectors
    const imgSelectors = [
        '.tm-article-image img',
        'article img',
        '.uk-article img',
        'meta[property="og:image"]',
        '.tm-main img'
    ];
    
    for (const selector of imgSelectors) {
        const el = $(selector).first();
        if (el.length) {
            const src = el.attr('content') || el.attr('src');
            if (src) {
                return resolveUrl(src);
            }
        }
    }
    
    return '';
}

function resolveUrl(src) {
    if (src.startsWith('http')) return src;
    if (src.startsWith('/')) return `https://www.nationalcrimeagency.gov.uk${src}`;
    return `https://www.nationalcrimeagency.gov.uk/${src}`;
}

function determineCategories(content, title) {
    const contentLower = content.toLowerCase();
    const titleLower = title.toLowerCase();
    const combinedText = contentLower + ' ' + titleLower;
    
    const categories = [];
    
    // Check for each category based on keywords
    for (const [category, keywords] of Object.entries(CATEGORY_KEYWORDS)) {
        if (keywords.some(keyword => combinedText.includes(keyword.toLowerCase()))) {
            categories.push(category);
        }
    }
    
    return categories;
}

function extractLocations(content) {
    const locations = new Set();

    // Postcodes
    const postcodes = content.match(/([A-Z]{1,2}\d{1,2}[A-Z]?\s\d[A-Z]{2})/g) || [];
    postcodes.forEach(pc => locations.add(pc.toUpperCase()));

    // Known locations
    UK_LOCATIONS.forEach(loc => {
        if (new RegExp(`\\b${loc}\\b`, 'i').test(content)) {
            locations.add(loc);
        }
    });

    // Contextual patterns
    const locPatterns = [
        /(?:in|near|from|at)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)/g,
        /([A-Z][a-z]+\s(?:City|Town|Village|County))\b/g,
        /[A-Z][a-z]+ (?:Street|Road|Avenue|Lane|Park|Square)/g,
        /(?:port of|area of|region of)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)/g
    ];

    locPatterns.forEach(pattern => {
        let match;
        while ((match = pattern.exec(content)) !== null) {
            const loc = match[1] ? match[1].trim() : match[0].trim();
            if (loc && loc.length > 3) {
                locations.add(loc);
            }
        }
    });

    return Array.from(locations);
}

function extractPeople(content, role) {
    const people = [];
    const namePatterns = [
        /(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b)(?:\s*,\s*(\d{1,2}))?(?:\s*,\s*(?:from|of)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*))?\s+(?:was|has been|had been|is|were|have been)\s+(?:arrested|charged|convicted|jailed|sentenced|found guilty)/g,
        /(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b)(?:\s*,\s*(\d{1,2}))?(?:\s*,\s*(?:from|of)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*))?\s+(?:pleaded|admitted)/g
    ];

    namePatterns.forEach(pattern => {
        let match;
        while ((match = pattern.exec(content)) !== null) {
            const name = match[1];
            const age = match[2] ? parseInt(match[2]) : extractAge(getContext(content, name, 150));
            const location = match[3] || extractLocationFromContext(getContext(content, name, 150));
            
            const context = getContext(content, name, 150);
            if (isRelevantPerson(context, role)) {
                people.push({
                    name: name,
                    age: age,
                    location: location,
                    role: role,
                    context: context.replace(/\s+/g, ' ')
                });
            }
        }
    });

    // General name pattern as a fallback
    const generalNamePattern = /(\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b)/g;
    const names = [...new Set(content.match(generalNamePattern) || [])];

    names.forEach(name => {
        // Skip if already found
        if (people.some(p => p.name === name)) return;
        
        const context = getContext(content, name, 150);
        if (isRelevantPerson(context, role)) {
            people.push({
                name: name,
                age: extractAge(context),
                location: extractLocationFromContext(context),
                role: role,
                context: context.replace(/\s+/g, ' ')
            });
        }
    });

    return people;
}

function isRelevantPerson(context, role) {
    const lowerContext = context.toLowerCase();
    const keywords = role === 'victim' ? VICTIM_KEYWORDS : PERP_KEYWORDS;
    return Array.from(keywords).some(kw => lowerContext.includes(kw));
}

function extractAge(context) {
    const agePatterns = [
        /\b(?:aged|age)\s+(\d{1,2})\b/,
        /(\d{1,2})\s+(?:year|years)\s+old/,
        /(\d{1,2})-year-old/
    ];
    
    for (const pattern of agePatterns) {
        const match = context.match(pattern);
        if (match) {
            return parseInt(match[1]);
        }
    }
    
    return null;
}

function extractLocationFromContext(context) {
    const locationPatterns = [
        /(?:from|in|of|residing in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)/,
        /(?:address in|house in|property in)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)/
    ];
    
    for (const pattern of locationPatterns) {
        const match = context.match(pattern);
        if (match) {
            return match[1];
        }
    }
    
    return null;
}

function extractOrganizations(content) {
    const orgs = new Set();

    LAW_ENFORCEMENT_ORGS.forEach(org => {
        if (content.includes(org)) orgs.add(org);
    });

    const orgPatterns = [
        /([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(Police|Unit|Task Force|Agency|Force)\b/g,
        /(?:working with|partnered with|alongside)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)/g,
        /(?:Operation|op)\s+([A-Z][a-z]+)/g,
        /([A-Z][A-Z0-9]+)\s+(?:officers|investigation|operation)/g
    ];

    orgPatterns.forEach(pattern => {
        let match;
        while ((match = pattern.exec(content)) !== null) {
            const org = match[1] ? match[1] : (match[0] || '');
            if (org && org.length > 2) orgs.add(org);
        }
    });

    return Array.from(orgs);
}

function extractTimeline(content, $) {
    const dates = new Set();
    
    // Extract meta date
    const metaDate = $('meta[name="date"]').attr('content') || 
                     $('meta[property="article:published_time"]').attr('content');
    if (metaDate) {
        try {
            const formattedDate = new Date(metaDate).toLocaleDateString('en-GB', {
                day: '2-digit',
                month: 'long',
                year: 'numeric'
            });
            dates.add(formattedDate);
        } catch (e) {
            // Continue if date parsing fails
        }
    }
    
    // Extract date from content
    const datePatterns = [
        /\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}/g,
        /\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}/g,
        /(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,\s+\d{4}/g,
        /\d{4}-\d{2}-\d{2}/g,
        /(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+\w+\s+\d{1,2},\s+\d{4}/g
    ];

    datePatterns.forEach(pattern => {
        let match;
        while ((match = pattern.exec(content)) !== null) {
            dates.add(match[0]);
        }
    });
    
    // Look for year mentions with context
    const yearMentions = content.match(/\b(in|during|since|from|until|by|before|after)\s+(\d{4})\b/g) || [];
    yearMentions.forEach(mention => {
        dates.add(mention);
    });
    
    // Extract "today" or "yesterday" with context
    const relativeDate = $('time').text().trim();
    if (relativeDate) {
        dates.add(relativeDate);
    }
    
    // Get the last paragraph which often contains the article date
    const lastParagraph = $('article p, .uk-article p, .tm-main p').last().text().trim();
    const lastParaDate = extractDateFromString(lastParagraph);
    if (lastParaDate) {
        dates.add(lastParaDate);
    }
    
    return Array.from(dates);
}

function extractDateFromString(text) {
    const datePatterns = [
        /\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}/,
        /\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}/,
        /(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,\s+\d{4}/,
        /\d{4}-\d{2}-\d{2}/,
        /(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+\w+\s+\d{1,2},\s+\d{4}/
    ];

    for (const pattern of datePatterns) {
        const match = text.match(pattern);
        if (match) return match[0];
    }
    
    return null;
}

function extractSentences(content) {
    const sentences = [];
    const patterns = [
        /sentenced to\s+([^\.;]+)/gi,
        /jailed for\s+([^\.;]+)/gi,
        /imprisonment of\s+([^\.;]+)/gi,
        /(?:received|given) (?:a|an)\s+([^\.;]+)\s+(?:sentence|term|custodial)/gi,
        /ordered to (?:pay|forfeit|repay)\s+([^\.;]+)/gi,
        /(\d+[- ](?:year|month)(?:s)?\s+(?:sentence|imprisonment|jail term|custodial sentence))/gi,
        /(\d+\s+years?\s+(?:and|&)\s+\d+\s+months?)/gi
    ];

    patterns.forEach(pattern => {
        let match;
        while ((match = pattern.exec(content)) !== null) {
            const sentence = match[1].trim();
            if (sentence && !sentences.includes(sentence)) {
                sentences.push(sentence);
            }
        }
    });

    return sentences;
}

function extractCharges(content) {
    const charges = [];
    const patterns = [
        /(?:pleaded guilty to|admitted|convicted of|charged with)\s+([^\.;]+)/gi,
        /(?:charges of|accused of|committed)\s+([^\.;]+)/gi,
        /found guilty of\s+([^\.;]+)/gi,
        /arrested (?:on suspicion of|for)\s+([^\.;]+)/gi,
        /prosecuted for\s+([^\.;]+)/gi
    ];

    patterns.forEach(pattern => {
        let match;
        while ((match = pattern.exec(content)) !== null) {
            const charge = match[1].trim();
            if (charge && !charges.includes(charge) && charge.length > 5) {
                charges.push(charge);
            }
        }
    });

    return charges;
}

function extractFinancials(content) {
    const amounts = [];
    const moneyPatterns = [
        /£\s*([\d,]+(?:\.\d+)?)\s*(million|billion|k|thousand)?/g,
        /(\d[\d,]*(?:\.\d+)?)\s*(million|billion|k|thousand)?\s*pounds/gi,
        /(\d[\d,]*(?:\.\d+)?)\s*(million|billion|k|thousand)?\s*sterling/gi
    ];
    
    moneyPatterns.forEach(pattern => {
        let match;
        while ((match = pattern.exec(content)) !== null) {
            const value = parseFloat(match[1].replace(/,/g, ''));
            const multiplier = getMultiplier(match[2]);
            const originalText = match[0].trim();
            
            amounts.push({
                amount: value * multiplier,
                currency: 'GBP',
                context: getContext(content, originalText, 50),
                originalText: originalText
            });
        }
    });
    
    return amounts;
}

function getMultiplier(unit) {
    if (!unit) return 1;
    
    const multipliers = {
        thousand: 1e3,
        k: 1e3,
        million: 1e6,
        billion: 1e9
    };
    return multipliers[unit.toLowerCase()] || 1;
}

function extractDrugQuantities(content) {
    const drugs = [];
    const drugPatterns = [
        /(\d+(?:\.\d+)?)\s*(kg|kilo|kilos|kilogram|kilograms|grams?|tonnes?|lb|pounds?)\s+(?:of\s+)?(\w+)/gi,
        /(\d+(?:\.\d+)?)\s*(kg|kilo|kilos|kilogram|kilograms|grams?|tonnes?|lb|pounds?)\s+(?:worth of\s+)?(\w+)/gi,
        /(\w+)\s+weighing\s+(\d+(?:\.\d+)?)\s*(kg|kilo|kilos|kilogram|kilograms|grams?|tonnes?|lb|pounds?)/gi
    ];
    
    drugPatterns.forEach(pattern => {
        let match;
        while ((match = pattern.exec(content)) !== null) {
            let quantity, unit, substance;
            
            if (pattern.toString().includes('weighing')) {
                substance = match[1].toLowerCase();
                quantity = parseFloat(match[2]);
                unit = match[3].toLowerCase();
            } else {
                quantity = parseFloat(match[1]);
                unit = match[2].toLowerCase();
                substance = match[3].toLowerCase();
            }
            
            // Clean up substance names
            if (substance === 'class') {
                // Handle "Class A drugs" pattern
                const contextAfter = content.substring(match.index, match.index + 20);
                if (contextAfter.match(/class\s+[A-D]/i)) {
                    substance = contextAfter.match(/class\s+[A-D]\s+\w+/i)[0].toLowerCase();
                }
            }
            
            drugs.push({
                quantity: quantity,
                unit: unit,
                substance: substance,
                context: getContext(content, match[0], 50)
            });
        }
    });
    
    return drugs;
}

function getContext(text, term, windowSize) {
    const index = text.indexOf(term);
    if (index === -1) return '';
    const start = Math.max(0, index - windowSize);
    const end = Math.min(text.length, index + term.length + windowSize);
    return text.slice(start, end);
}

function extractDate(content, $) {
    // First check for date in the metadata
    const metaDate = $('meta[name="date"]').attr('content') || 
                     $('meta[property="article:published_time"]').attr('content');
    if (metaDate) {
        try {
            const date = new Date(metaDate);
            return date.toLocaleDateString('en-GB', {
                day: '2-digit',
                month: 'long',
                year: 'numeric'
            });
        } catch (e) {
            // Continue if date parsing fails
        }
    }
    
    // Check for explicit date in the content
    const datePatterns = [
        /\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}/,
        /\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}/,
        /(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,\s+\d{4}/,
        /\d{4}-\d{2}-\d{2}/,
        /(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+\w+\s+\d{1,2},\s+\d{4}/
    ];

    for (const pattern of datePatterns) {
        const match = content.match(pattern);
        if (match) return match[0];
    }
    
    // Check the last paragraph, which often contains the article date
    const lastParagraph = $('article p, .uk-article p, .tm-main p').last().text().trim();
    if (lastParagraph) {
        for (const pattern of datePatterns) {
            const match = lastParagraph.match(pattern);
            if (match) return match[0];
        }
    }
    
    // If we still don't have a date, look for a time element
    const timeText = $('time').text().trim();
    if (timeText && timeText.match(/\d/)) {
        return timeText;
    }
    
    // Default to current date if all else fails
    return new Date().toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'long',
        year: 'numeric'
    });
}

function extractCategories($) {
    // Try to extract categories from specific selectors
    const categoryTags = $('.tm-article-meta a, .category-tag, .category, .tags-links a')
        .map((i, el) => $(el).text().trim())
        .get()
        .filter((value, index, self) => self.indexOf(value) === index);
    
    if (categoryTags.length > 0) {
        return categoryTags;
    }
    
    return [];
}

function saveReports(reports, outputPath) {
    fs.writeFileSync(outputPath, JSON.stringify(reports, null, 2), 'utf8');
    return reports;
}

// Command-line execution
const [inputFolder, outputFolder] = process.argv.slice(2);
if (!inputFolder || !outputFolder) {
    console.log('Usage: node script.js <input-folder> <output-folder>');
    process.exit(1);
}

processFolder(inputFolder, outputFolder);