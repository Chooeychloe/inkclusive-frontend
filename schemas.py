from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class APIModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GrammarBody(APIModel):
    prompt: str = Field(min_length=1, max_length=20_000, description="Text to check. Maximum 20,000 characters.")

    @field_validator("prompt")
    @classmethod
    def reject_blank_prompt(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Text must contain at least one non-whitespace character.")
        return value


class GFLBody(GrammarBody):
    pronoun_map: dict[str, Literal["gender_fair", "female", "male"]] = Field(default_factory=dict, max_length=100)


class GrammarCorrection(APIModel):
    character_offset: int = Field(ge=0)
    character_endset: int = Field(ge=0)
    original_text: str
    message: str
    rationale: str
    category: str
    rule_id: str
    replacements: list[str]


class GrammarResponse(APIModel):
    original_text: str
    revised_text: str
    corrections: list[GrammarCorrection]


class GenderFairCorrection(APIModel):
    word_index: int | None = None
    character_offset: int = Field(ge=0)
    character_endset: int = Field(ge=0)
    original_text: str
    replacements: list[str]
    message: str
    rationale: str
    category: str
    rule_id: str
    examples: list[str] = Field(default_factory=list)


class GenderFairResponse(APIModel):
    original_text: str
    revised_text: str
    corrections: list[GenderFairCorrection]
    count: int = Field(ge=0)


class GenderTermCreate(APIModel):
    term: str = Field(min_length=1, max_length=200, examples=["chairman"])
    options: list[str] = Field(min_length=1, max_length=20, examples=[["chairperson", "chair"]])
    category: str = Field(default="Other", min_length=1, max_length=80)
    guidance: str = Field(default="", max_length=2_000)
    examples: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("term")
    @classmethod
    def clean_term(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Term cannot be blank.")
        return value

    @field_validator("options")
    @classmethod
    def clean_options(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values if value and value.strip()]
        if not cleaned:
            raise ValueError("At least one non-empty alternative is required.")
        return cleaned

    @field_validator("examples")
    @classmethod
    def clean_examples(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value and value.strip()]


class GenderTermUpdate(APIModel):
    options: list[str] | None = Field(default=None, min_length=1, max_length=20)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    guidance: str | None = Field(default=None, max_length=2_000)
    examples: list[str] | None = Field(default=None, max_length=20)

    @field_validator("options")
    @classmethod
    def clean_options(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        cleaned = [value.strip() for value in values if value and value.strip()]
        if not cleaned:
            raise ValueError("At least one non-empty alternative is required.")
        return cleaned

    @field_validator("examples")
    @classmethod
    def clean_examples(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        return [value.strip() for value in values if value and value.strip()]

    @model_validator(mode="after")
    def require_an_update(self):
        if self.options is None and self.category is None and self.guidance is None and self.examples is None:
            raise ValueError("Provide at least one field to update.")
        return self


class GenderTermRecord(APIModel):
    term: str
    options: list[str]
    category: str = "Other"
    guidance: str = ""
    examples: list[str] = Field(default_factory=list)


class GenderTermBulkCreate(APIModel):
    terms: list[GenderTermCreate] = Field(min_length=1, max_length=500)


class GenderTermBulkResult(APIModel):
    created: int = Field(ge=0)


class GenderTermBulkDelete(APIModel):
    terms: list[str] = Field(min_length=1, max_length=500)

    @field_validator("terms")
    @classmethod
    def clean_terms(cls, values: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(term.strip() for term in values if term and term.strip()))
        if not cleaned:
            raise ValueError("Provide at least one term to delete.")
        return cleaned


class GenderTermBulkDeleteResult(APIModel):
    deleted: int = Field(ge=0)


class CountResponse(APIModel):
    count: int = Field(ge=0)


class AdminLoginBody(APIModel):
    password: str = Field(min_length=1, max_length=1024)


class AdminPasswordChange(APIModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class AdminLoginResponse(APIModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(gt=0)
