from pydantic import BaseModel, Field, RootModel
from typing import Dict, List
from typing import Literal

class GrammarBody(BaseModel):
    prompt: str
    
class GFLBody(BaseModel):
    prompt: str 
    pronoun_map: dict[str, Literal['gender_fair', 'female', 'male']] = {
        "Alex": "gender_fair",
        "John": "male",
        "Jane": "female"
    }

class GenderTermCreate(BaseModel):
    term: str = Field(..., example="chairman")
    options: List[str] = Field(..., example=["chairperson", "chair"])
    category: str = "Other"
    guidance: str = ""
    examples: List[str] = []


class GenderTermUpdate(BaseModel):
    options: List[str] = Field(..., example=["chairperson", "moderator"])
    category: str | None = None
    guidance: str | None = None
    examples: List[str] | None = None



class GenderTermBulkCreate(BaseModel):
    terms: List[GenderTermCreate]
