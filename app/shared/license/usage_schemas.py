from pydantic import BaseModel

class UsageReportRequest(BaseModel):
    tokens_input: int
    tokens_output: int
    source: str = "wp-plugin"
    site_url: str = ""
