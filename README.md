# NCA News Article Processing Workflow

This repository contains an n8n workflow and set of parser scripts designed to extract, process, and analyze news articles from the National Crime Agency (NCA) website.

## Overview

The workflow automatically:

1. Scrapes news article listings from the NCA website
2. Downloads complete article content
3. Processes articles to extract structured data
4. Identifies entities, locations, and key information
5. Organizes the results in a structured format

## Components

### n8n Workflow

`NCA Workflow.json` - The complete n8n workflow configuration that can be imported into an n8n instance.

### Local Parsers

- **localParser.js** - Initial parser that extracts basic article metadata from listing pages
- **localFullArticleParser.js** - Enhanced parser that processes full article content and extracts structured data
- **nlp_extractor.py** - Python script for advanced NLP processing of article content
- **nlp_extractor_gpu.py** - GPU-accelerated version of the NLP extractor
- **process_articles_gpu.py** - Batch processing script for handling multiple articles with GPU acceleration

## Extracted Data

The parsers extract the following types of information:

- Article metadata (title, date, intro, etc.)
- Locations mentioned in articles
- Organizations and law enforcement agencies
- Timeline of events
- Perpetrators and their details
- Criminal sentences and charges
- Monetary amounts
- Drug quantities
- Article categorization

## Setup Requirements

### n8n Setup

1. Install n8n: `npm install n8n -g`
2. Import the workflow: Navigate to n8n → Settings → Import from file
3. Place parser files in the n8n home directory

### Parser Dependencies

JavaScript parsers require:
- Node.js
- cheerio
- fs and path modules

Python parsers require:
- Python 3.8+
- spaCy with the `en_core_web_lg` model
- Transformers library
- BeautifulSoup4
- Other dependencies listed in the script headers

## Usage

1. Start n8n with: `n8n start`
2. Navigate to the workflows tab
3. Open the NCA Workflow
4. Run the workflow manually or set up a schedule

## Folder Structure

- `/Local Parsers/` - Contains all parser scripts
- `NCA Workflow.json` - The n8n workflow configuration

## License

This project is created for educational and research purposes.

## Acknowledgments

- National Crime Agency for their public news articles
- n8n for the workflow automation platform
