"""全局配置 - 基于 pydantic-settings，从环境变量 / .env 文件加载"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"

    # Internal AI Gateway (takes precedence over OPENAI_* when configured)
    ai_gateway_token: str = ""
    ai_gateway_base_url: str = ""
    ai_gateway_bizid: str = "hunter"
    ai_gateway_ability_key: str = "gcp-claude-sonnet-4-6"

    # 翻译专用模型（留空则复用全局 LLM 配置；建议用更强的模型如 gpt-4o）
    translate_model: str = ""
    translate_api_key: str = ""
    translate_base_url: str = ""

    # Embedding（默认复用 LLM 的 API Key，也可单独配置）
    embedding_api_key: str = ""
    embedding_base_url: str = ""
    embedding_model: str = "text-embedding-3-small"

    # 数据源
    reddit_subreddits: str = "LocalLLaMA,MachineLearning,artificial"
    enable_reddit: bool = False
    hn_min_score: int = 50
    twitter_api_key: str = ""
    twitter_kol_list: str = ""
    firecrawl_api_key: str = ""
    twitter_list_url: str = "https://x.com/i/lists/1585430245762441216"
    nitter_mirror_url: str = "https://nitter.net"

    # 自定义 RSS 源（格式: name1=url1,name2=url2）
    rss_feeds: str = ""

    # GitHub 趋势去重缓存天数；日报最多推荐 3 个高相关 trending 项目
    github_trending_dedup_days: int = 3
    github_trending_max_items: int = 3

    # HuggingFace Papers
    hf_papers_min_upvotes: int = 5

    # Product Hunt
    producthunt_api_token: str = ""
    producthunt_min_votes: int = 50

    # 数据库
    postgres_url: str = "postgresql://postgres:postgres@localhost:5432/ainews"

    # 输出
    output_dir: str = "./output"
    output_format: str = "markdown"

    # Webhook 推送 (v0.5)
    slack_webhook_url: str = ""
    discord_webhook_url: str = ""
    feishu_webhook_url: str = ""

    # 邮件推送 (v0.5)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    newsletter_recipients: str = ""

    # Feishu application bot (long connection, not a custom-bot webhook)
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_allowed_chat_ids: str = ""
    feishu_target_chat_id: str = ""
    feishu_trigger_cooldown_seconds: int = 3600

    # Alibaba Cloud OSS
    oss_endpoint: str = ""
    oss_resource_bucket: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_prefix: str = "ai-news-agent"
    oss_custom_domain: str = ""

    # Cloud service
    service_host: str = "0.0.0.0"
    service_port: int = 8080

    # 审核模式 (v0.5): "auto" 或 "human"
    review_mode: str = "auto"

    # 监控 (v1.0)
    langsmith_api_key: str = ""
    langsmith_project: str = "ai-news-agent"

    # Pipeline
    report_mode: str = "daily"  # daily / weekly
    max_items_per_run: int = 50
    max_items_per_source: int = 15
    arxiv_max_items: int = 5  # ArXiv 单独限制，避免论文占比过高
    min_items_per_source: int = 3
    min_items_per_rss_feed: int = 2  # 每个 RSS 子源保底，避免博客变多后被挤掉
    max_items_per_rss_feed: int = 3
    top_k_featured: int = 10
    min_importance_score: int = 3  # 低于此分数的条目不纳入日报（过滤非新闻内容）
    min_items_to_write: int = 5
    log_level: str = "INFO"

    # Profile 化资讯评分
    scoring_profile: str = "tech-news"  # profile 名称或 auto
    scoring_profiles_dir: str = "profiles"
    scoring_batch_size: int = 10
    scoring_max_concurrent: int = 3
    scoring_max_retries: int = 3
    scoring_max_items: int = 20

    @property
    def output_path(self) -> Path:
        p = Path(self.output_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def subreddit_list(self) -> list[str]:
        return [s.strip() for s in self.reddit_subreddits.split(",") if s.strip()]

    @property
    def rss_feed_list(self) -> list[tuple[str, str]]:
        """解析 rss_feeds 配置，返回 [(name, url), ...]"""
        result = []
        for item in self.rss_feeds.split(","):
            item = item.strip()
            if "=" in item:
                name, url = item.split("=", 1)
                result.append((name.strip(), url.strip()))
        return result

    @property
    def feishu_allowed_chats(self) -> set[str]:
        return {
            chat_id.strip()
            for chat_id in self.feishu_allowed_chat_ids.split(",")
            if chat_id.strip()
        }

    @property
    def llm_configured(self) -> bool:
        return bool(self.ai_gateway_token or self.openai_api_key)

    @property
    def llm_model_name(self) -> str:
        if self.ai_gateway_token:
            return self.ai_gateway_ability_key
        return self.openai_model

    @property
    def llm_base_url(self) -> str:
        if self.ai_gateway_token:
            return f"{self.ai_gateway_base_url.rstrip('/')}/v1"
        return self.openai_base_url



settings = Settings()
