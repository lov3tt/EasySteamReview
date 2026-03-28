# EasySteamReview
A Data Analyst Tool to see review of games through the Steam Store within the scope of 30 days, picking up on keywords involve cheating, hacking, scamming and other to see the game credibility and stability.

### Project Scope: Player Review Analysis Dashboard for Cheating and Moderation Insights

**Background:**  
The gaming industry has grown exponentially over the past decade, with millions of players engaging in multiplayer games across various platforms. Issues like cheating and player moderation have become significant challenges for game developers and platform owners. Players often express their experiences, frustrations, or praises through reviews on platforms like Steam. These reviews contain valuable insights into issues such as cheating, moderator behavior, and the overall health of a gaming community.

**Objective:**  
The objective is to build a tool that analyzes player reviews from the Steam platform to identify trends, sentiment, and specific mentions related to cheating and moderation. This tool will provide developers, game publishers, and moderators with actionable insights to improve their games and communities.

---

### Competitive Analysis

The gaming analytics market is highly competitive, with various tools and platforms offering review analysis, sentiment detection, and keyword tracking. However, most of these tools are generic and do not focus specifically on cheating or moderation-related issues.

**Competitive Landscape:**
1. **Existing Solutions:**
   - Platforms like Steam already provide basic review metrics (e.g., positive/negative reviews).
   - Tools like Reddit and Discord analytics platforms offer keyword tracking but lack integration with gaming-specific APIs.
   - No dedicated tool exists that focuses on cheating or moderation-related keywords in player reviews.

2. **Gap Identification:**
   - Current solutions do not analyze reviews for specific keywords related to cheating or moderation.
   - There is a lack of tools that provide visual insights (e.g., graphs, dashboards) to track the frequency and sentiment of these mentions over time.

3. **Proposed Solution:**
   - A dashboard that aggregates Steam user reviews, analyzes them for cheating/moderation-related keywords using NLP techniques, and provides actionable insights.
   - Integration with Steam APIs (Steam User Reviews API, SteamDB API, SteamSpy API) to fetch data in real-time or near-real-time.

---

### Project Scope Breakdown

#### 1. **Data Collection:**
   - Use the Steam User Reviews API to pull user reviews for specific games or all games on Steam.
   - Use SteamDB and SteamSpy APIs to supplement with additional metadata (e.g., number of players, game popularity).

#### 2. **Keyword Extraction Using NLP:**
   - Implement Natural Language Processing techniques using libraries like NLTK to identify mentions of cheating-related keywords such as:
     - "cheating"
     - "cheated"
     - "cheat"
     - "moderators"
     - "moderation."
   - Use regular expressions and entity recognition to detect variations in language (e.g., "hacked," "scam," or "unfair").

#### 3. **Dashboard Features:**
   - **Keyword Tracking:** A dashboard view showing the frequency of cheating/moderation-related keywords over time.
   - **Sentiment Analysis:** Analyze the sentiment of reviews mentioning cheating or moderation to understand player frustration or satisfaction.
   - **Case Tracking:** Allow users to click on specific keyword mentions and view the full review for context.
   - **Visual Graphs:** Create graphs (e.g., line charts, bar graphs) showing the number of positive/negative reviews over time, with a focus on cheating-related keywords as a percentage of total reviews.

#### 4. **User Interface:**
   - A clean and intuitive dashboard interface built using Python visualization libraries like Matplotlib or Seaborn.
   - Integration with FastAPI for API development to allow programmatic access to the data.

---

### Business Case Justification

1. **Market Need:**
   - Cheating is a significant issue in online gaming, leading to player dissatisfaction and loss of trust in games.
   - Developers and publishers need insights into how players perceive cheating and moderation in their games to improve community management.

2. **Value Proposition:**
   - The tool provides actionable insights into cheating and moderation trends across Steam games.
   - Helps developers identify problematic games or communities that require intervention.
   - Saves time by automating keyword extraction and sentiment analysis, allowing moderators and developers to focus on high-priority issues.

3. **Monetization Potential:**
   - Offer the tool as a subscription service for game developers and publishers.
   - Provide premium features like advanced analytics, custom alerts, or integration with third-party moderation tools.

---

### Technical Specifications

1. **Technology Stack:**
   - **Programming Language:** Python
   - **API Framework:** FastAPI (for building the dashboard API)
   - **NLP Library:** NLTK
   - **Visualization Libraries:** Matplotlib, Seaborn, or Plotly.
   - **Database:** SQLite or PostgreSQL for storing processed data.

2. **Implementation Steps:**
   3. Set up API integrations with Steam User Reviews, SteamDB, and SteamSpy APIs.
   4. Develop a keyword extraction module using NLP techniques.
   5. Build the dashboard interface using Python visualization libraries.
   6. Test the tool with sample data to ensure accuracy and performance.

---

### Conclusion

This project aims to address a critical gap in the gaming analytics space by providing developers, publishers, and moderators with insights into cheating and moderation-related issues through player reviews. By leveraging APIs, NLP techniques, and visualization tools, this dashboard will offer actionable insights that can help improve game communities and player experiences.
