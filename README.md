\# AI Fomonomo

FOMO No More! This project picks out AI news from trusted sources daily, and compiles them into a Top 5 that you should know.



\## How It Works

Via GitHub Actions, a script fetches news via RSS feed from the sites below. It then gets Gemini to condense a Top 5 according to novelty, real-world impact, diversity of topics, and avoidance of duplication. The prompt is available in src/fetch\_top5.py



For each article, it creates a headline, summary, insights and source. The value here is the Insights: Why does it matter to the reader? An "image card" is then generated, and emailed to miketee@gmail.com for custom upload to IG @ai\_fomonomo.





\## AI News Sites

\* "https://techcrunch.com/category/artificial-intelligence/feed/",

\* "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",

\* "https://www.technologyreview.com/feed/",





\# Future plans

\* More news sources

\* More user profile targeting - ie content relevant to business owners or product managers?

\* Automation direct upload to IG



