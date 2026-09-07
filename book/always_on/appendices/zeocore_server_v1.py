"""Optional Zeocore process. Run with a separate Python containing zeocore[mcp]."""

from pydantic import BaseModel, ConfigDict, Field
from zeo_core.adapters.mcp import register_tool, run
from zeo_core.contracts import CapabilityResult
from zeo_core.tools import BaseZeoTool, ToolContext


class ReportText(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str = Field(max_length=4096)


class Counts(BaseModel):
    word_count: int
    char_count: int


class WordCountTool(BaseZeoTool):
    name = "word_count"
    version = "1.0.0"

    def run(self, request: ReportText, ctx: ToolContext) -> CapabilityResult[Counts]:
        return CapabilityResult.ok(
            data=Counts(word_count=len(request.text.split()), char_count=len(request.text)),
            msg="Report text counted",
        )


if __name__ == "__main__":
    register_tool(WordCountTool())
    run(name="lucy-zeocore-example")
