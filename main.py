import argparse
from typing import Optional

from dotenv import load_dotenv

from database import DatabaseClient
from llm_client import LLMClient
from prompt_builder import build_prompt
from query_parser import QueryParser
from result_formatter import ResultFormatter


DEFAULT_QUERY = "按照客户类型查询平均订单金额和订单数量"


class ChatBIMVP:
    """ChatBI MVP 流程测试封装类。"""

    def __init__(self):
        """初始化 MVP 流程中需要用到的各个模块。"""
        self.query_parser = QueryParser()
        self.llm_client = LLMClient()
        self.database = DatabaseClient()
        self.result_formatter = ResultFormatter()

    def run(self, query: str) -> Optional[str]:
        """
        执行完整 MVP 测试流程：
        query_parser -> prompt_builder -> llm_client -> database -> result_formatter。
        """
        print("=" * 80)
        print("ChatBI MVP 流程测试")
        print("=" * 80)
        print(f"[输入问题] {query}")

        # 步骤 1：query_parser 校验用户输入是否合法。
        is_valid = self.query_parser.parse(query)
        if not is_valid:
            print("[query_parser] 用户输入不合法")
            return None
        print("[query_parser] 用户输入合法")

        # 步骤 2：prompt_builder 根据用户问题构造 LLM 提示词。
        system_prompt, user_prompt = build_prompt(query)
        print("[prompt_builder] 提示词生成完成")
        print(f"[prompt_builder] system prompt 长度：{len(system_prompt)}")
        print(f"[prompt_builder] user prompt 长度：{len(user_prompt)}")

        # 步骤 3：llm_client 调用大模型，把自然语言问题转换成 SQL。
        try:
            sql = self.llm_client.generate_sql(system_prompt, user_prompt)
        except Exception as exc:
            print("[llm_client] SQL 生成失败")
            print(self.result_formatter.format_error(str(exc)))
            return None

        print("[llm_client] SQL 生成完成")
        print("-" * 80)
        print(sql)
        print("-" * 80)

        # 步骤 4：database 执行 SQL，返回字段名和查询结果。
        try:
            columns, rows = self.database.execute(sql)
        except Exception as exc:
            print("[database] SQL 执行失败")
            print(self.result_formatter.format_error(str(exc)))
            return sql

        print("[database] SQL 执行完成")
        print(f"[database] 返回行数：{len(rows)}")

        # 步骤 5：result_formatter 格式化查询结果，输出可读表格。
        print("[result_formatter] 查询结果格式化完成")
        print(self.result_formatter.format(columns, rows))

        return sql


def main() -> None:
    load_dotenv()

    arg_parser = argparse.ArgumentParser(description="运行 ChatBI MVP 流程测试。")
    arg_parser.add_argument(
        "query",
        nargs="?",
        default=DEFAULT_QUERY,
        help="需要执行的自然语言查询问题。",
    )
    args = arg_parser.parse_args()

    chatbi_mvp = ChatBIMVP()
    chatbi_mvp.run(args.query)


if __name__ == "__main__":
    main()
