INDUSTRY_GUIDANCE_MAP = {
    "retail": """
When designing the report structure:
- Include sections related to sales performance, revenue trends, and customer behavior.
- Financial analysis typically focuses on revenue, costs, margins, and profitability.
- Customer, product, and market perspectives are important.
- Operational considerations such as inventory or efficiency may be relevant.
""",

    "finance": """
When designing the report structure:
- Emphasize financial performance, profitability, and financial stability.
- Include perspectives on risk, compliance, or governance where appropriate.
- Financial metrics and performance analysis are central.
- Avoid operational or supply-chain perspectives unless explicitly requested.
""",

    "manufacturing": """
When designing the report structure:
- Include sections related to production performance and operational efficiency.
- Consider supply chain, inventory management, and cost structure perspectives.
- Financial performance is often closely linked to operational outcomes.
""",

    "technology": """
When designing the report structure:
- Include sections related to product performance, growth, and customer usage.
- Consider scalability, innovation, and recurring revenue perspectives.
- Operational efficiency may relate to development, delivery, or platform performance.
""",

    "generic": """
When designing the report structure:
- Use broadly applicable professional business report conventions.
- Focus on performance overview, financial perspective, and strategic considerations.
"""
}


def get_industry_guidance(industry: str) -> str:
    "return industry guidance from key"
    if not industry:
        return INDUSTRY_GUIDANCE_MAP["generic"]

    key = industry.lower().strip()
    return INDUSTRY_GUIDANCE_MAP.get(key, INDUSTRY_GUIDANCE_MAP["generic"])