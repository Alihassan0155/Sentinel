from pydantic import BaseModel, Field, model_validator


class ProfileUpdate(BaseModel):
    skills: list[str] = Field(default_factory=list)
    degree: str | None = None
    interests: list[str] = Field(default_factory=list)
    desired_roles: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    preferred_categories: list[str] = Field(default_factory=list)
    available_resources: list[str] = Field(default_factory=list)
    salary_min: int | None = Field(
        default=None,
        gt=0,
        description="Minimum preferred annual salary in USD.",
    )
    salary_max: int | None = Field(
        default=None,
        gt=0,
        description="Maximum preferred annual salary in USD.",
    )

    @model_validator(mode="after")
    def validate_salary_range(self):
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("salary_min must not exceed salary_max")
        return self


class ProfileResponse(ProfileUpdate):
    id: int | None = None

    model_config = {"from_attributes": True}
