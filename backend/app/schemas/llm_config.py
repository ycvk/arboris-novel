from pydantic import BaseModel, Field, HttpUrl


class LLMConfigBase(BaseModel):
    llm_provider_url: HttpUrl | None = Field(
        default=None, description="自定义 LLM 服务地址"
    )
    llm_provider_api_key: str | None = Field(
        default=None, description="自定义 LLM API Key"
    )
    llm_provider_model: str | None = Field(default=None, description="自定义模型名称")


class LLMConfigCreate(LLMConfigBase):
    pass


class LLMConfigRead(LLMConfigBase):
    user_id: int

    class Config:
        """Pydantic 模型配置."""

        from_attributes = True
