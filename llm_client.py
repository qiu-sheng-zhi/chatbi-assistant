import os
import re

from openai import OpenAI

from prompt_builder import build_prompt

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL"),
)
class LLMClient:
    def generate_sql(self,system_prompt: str, prompt: str) -> str:
        """
        根据提示词，调用 LLM 生成 SQL
        """

        response = client.chat.completions.create(
            model=os.getenv("LLM_MODEL"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
                ],
            temperature=0.1,
            max_tokens=1024
        )

        raw_output = response.choices[0].message.content.strip()
        sql = re.sub(r'```sql|```', '', raw_output).strip()
        return sql