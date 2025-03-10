const fs = require('fs');
const cheerio = require('cheerio');
const path = require('path');

// Utility function to clean text by removing extra whitespace
function cleanText(text) {
  return text ? text.replace(/\s+/g, ' ').trim() : '';
}

// Get the file path from command line arguments
const filePath = process.argv[2];

// Check if file path is provided
if (!filePath) {
  console.error("Error: No file path provided. Usage: node localParser.js <path-to-html-file>");
  process.exit(1);
}

try {
  // Read the HTML file from the specified path
  const html = fs.readFileSync(filePath, 'utf8');
  const $ = cheerio.load(html);
  const articles = [];
  
  // Select each article container; adjust selectors based on your page structure
  $('.items-row .item.column-1').each((i, element) => {
    // Primary extraction: title and link from .page-header h3 a
    const titleElement = $(element).find('.page-header h3 a');
    const title = cleanText(titleElement.text());
    let link = titleElement.attr('href') || '';
    
    // If the link is not found, log a message and try a fallback
    if (!link) {
      console.log(`No link found using '.page-header h3 a' for article with title: "${title}"`);
      // Fallback: use the first <a> tag in the article container
      link = $(element).find('a').first().attr('href') || '';
    }
    
    // If link is relative, prepend the base URL
    if (link && !link.startsWith('http')) {
      link = 'https://www.nationalcrimeagency.gov.uk' + link;
    }
    
    // Extract intro text and publication date, cleaning them
    const intro = cleanText($(element).find('.intro-text p').text());
    const date = cleanText($(element).find('.intro-date').text());
    
    // Optionally, extract image URL from the item-image container
    const imageElement = $(element).find('.pull-left.item-image a img');
    let imageUrl = imageElement.attr('src') || '';
    if (imageUrl && !imageUrl.startsWith('http')) {
      imageUrl = 'https://www.nationalcrimeagency.gov.uk' + imageUrl;
    }
    
    // Try multiple selectors for categories
    let category = '';
    // Common category selectors to try
    const categorySelectors = [
      '.article-info .category-name',
      '.tags-links',
      '.category',
      '.article-info-term',
      '.tag-category',
      '.tags',
      '.article-meta .category'
    ];
    
    for (const selector of categorySelectors) {
      const categoryElement = $(element).find(selector);
      if (categoryElement.length) {
        category = cleanText(categoryElement.text());
        if (category && !['article info', 'details', 'category'].includes(category.toLowerCase())) {
          break;
        }
      }
    }
    
    // If no category found with selectors, look for any element that might contain category info
    if (!category) {
      $(element).find('*').each(function() {
        const text = $(this).text().trim();
        const classAttr = $(this).attr('class') || '';
        // Check if the element or its class name suggests it contains category information
        if ((classAttr.includes('cat') || classAttr.includes('tag')) &&
            text && text.length < 30 && !['article info', 'details'].includes(text.toLowerCase())) {
          category = cleanText(text);
          return false; // break the loop
        }
      });
    }
    
    // Only add the article if both title and link are present
    if (title && link) {
      articles.push({
        title,
        url: link,
        intro,
        date,
        imageUrl,
        category
      });
    }
  });
  
  // Output valid JSON (only the JSON string is printed to stdout)
  console.log(JSON.stringify({ articles }, null, 2));
} catch (error) {
  console.error("Error reading or parsing file:", error.message);
  process.exit(1);
}