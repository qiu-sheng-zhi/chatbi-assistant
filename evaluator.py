"""
评估模块

负责运行测试用例集，对比生成 SQL 与预期 SQL 的执行结果，
计算 Execution Accuracy 并输出评估报告。

评估判定标准：
- Execution Accuracy：生成 SQL 的执行结果与预期 SQL 的执行结果在数据层面等价
- Exact Match Accuracy：生成 SQL 的字符串与预期 SQL 完全一致（仅供参考，非主要指标）
"""

import json
import re
from typing import Callable, Optional
from database import DatabaseClient


class Evaluator:
    """SQL 生成评估器"""

    def __init__(self, db_client: Optional[DatabaseClient] = None):
        """
        Args:
            db_client: 数据库客户端实例，如未传入则自动创建
        """
        self.db = db_client or DatabaseClient()

    def load_test_cases(self, path: str = "test_cases.json") -> list[dict]:
        """从 JSON 文件加载测试用例"""
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def evaluate_one(
        self,
        case: dict,
        sql_generator: Callable[[str], str]
    ) -> dict:
        """
        评估单个测试用例

        Args:
            case: 测试用例字典，包含 question、expected_sql 等字段
            sql_generator: 接收问题字符串、返回生成 SQL 的可调用对象

        Returns:
            包含评估结果的字典
        """
        question = case["question"]
        expected_sql = case["expected_sql"]

        result = {
            "id": case.get("id", "unknown"),
            "category": case.get("category", "unknown"),
            "question": question,
            "expected_sql": expected_sql,
            "generated_sql": None,
            "exact_match": False,
            "execution_match": False,
            "error": None,
            "detail": {}
        }

        # 1. 生成 SQL
        try:
            generated_sql = sql_generator(question)
            result["generated_sql"] = generated_sql
            result["exact_match"] = self._normalize_sql(generated_sql) == self._normalize_sql(expected_sql)
        except Exception as e:
            result["error"] = f"SQL 生成失败：{e}"
            return result

        # 2. 执行预期 SQL 获取基准结果
        try:
            exp_columns, exp_results = self.db.execute(expected_sql)
        except Exception as e:
            result["error"] = f"预期 SQL 执行失败：{e}"
            return result

        # 3. 执行生成 SQL 获取结果
        try:
            gen_columns, gen_results = self.db.execute(generated_sql)
        except Exception as e:
            result["error"] = f"生成 SQL 执行失败：{e}"
            result["detail"] = {
                "expected_columns": exp_columns,
                "expected_row_count": len(exp_results)
            }
            return result

        # 4. 对比执行结果
        result["execution_match"] = self._results_equivalent(
            gen_columns, gen_results, generated_sql,
            exp_columns, exp_results, expected_sql
        )

        result["detail"] = {
            "expected_columns": exp_columns,
            "expected_row_count": len(exp_results),
            "generated_columns": gen_columns,
            "generated_row_count": len(gen_results)
        }

        return result

    def evaluate_all(
        self,
        cases: list[dict],
        sql_generator: Callable[[str], str]
    ) -> list[dict]:
        """批量评估所有测试用例"""
        return [self.evaluate_one(case, sql_generator) for case in cases]

    def generate_report(self, results: list[dict]) -> str:
        """
        生成评估报告

        Args:
            results: evaluate_all 返回的结果列表

        Returns:
            格式化的文本报告
        """
        total = len(results)
        execution_correct = sum(1 for r in results if r["execution_match"])
        exact_correct = sum(1 for r in results if r["exact_match"])
        error_count = sum(1 for r in results if r["error"] is not None)

        # 按难度分类统计
        categories = {}
        for r in results:
            cat = r["category"]
            if cat not in categories:
                categories[cat] = {"total": 0, "correct": 0, "error": 0}
            categories[cat]["total"] += 1
            if r["execution_match"]:
                categories[cat]["correct"] += 1
            if r["error"]:
                categories[cat]["error"] += 1

        lines = [
            "=" * 60,
            "ChatBI Text2SQL 评估报告",
            "=" * 60,
            f"总用例数：{total}",
            f"Execution Accuracy：{execution_correct}/{total} = {execution_correct/total*100:.1f}%",
            f"Exact Match Accuracy：{exact_correct}/{total} = {exact_correct/total*100:.1f}%",
            f"执行失败数：{error_count}",
            "",
            "按难度分类统计：",
        ]

        for cat in ["simple", "medium", "complex"]:
            if cat in categories:
                stat = categories[cat]
                acc = stat["correct"] / stat["total"] * 100 if stat["total"] > 0 else 0
                lines.append(f"  {cat:8s}: {stat['correct']}/{stat['total']} = {acc:.1f}% (失败 {stat['error']})")

        lines.extend(["", "详细结果："])
        for r in results:
            status = "通过" if r["execution_match"] else ("失败" if r["error"] else "不匹配")
            lines.append(f"\n[{r['id']}] {r['category']:8s} | {status}")
            lines.append(f"  问题：{r['question']}")
            if r["error"]:
                lines.append(f"  错误：{r['error']}")
            else:
                lines.append(f"  生成 SQL：{r['generated_sql']}")
                if not r["execution_match"]:
                    lines.append(f"  预期行数：{r['detail'].get('expected_row_count', 'N/A')}, "
                               f"生成行数：{r['detail'].get('generated_row_count', 'N/A')}")

        return "\n".join(lines)

    def _normalize_sql(self, sql: str) -> str:
        """标准化 SQL 字符串，用于 Exact Match 比较"""
        return " ".join(sql.lower().split())

    def _results_equivalent(
        self,
        gen_columns: list,
        gen_results: list,
        gen_sql: str,
        exp_columns: list,
        exp_results: list,
        exp_sql: str
    ) -> bool:
        """
        判定两组执行结果是否等价

        比较策略：
        1. 列数必须相同
        2. 行数必须相同
        3. 维度列检查列名，聚合/计算指标列只比较值，不强制匹配别名
        4. 对结果排序后逐行比对（忽略行顺序）
        """
        if len(gen_columns) != len(exp_columns):
            return False

        if len(gen_results) != len(exp_results):
            return False

        check_column_flags = self._get_column_name_check_flags(exp_sql, gen_sql)
        if len(check_column_flags) != len(exp_columns):
            return False

        for i, should_check in enumerate(check_column_flags):
            if should_check and gen_columns[i].lower() != exp_columns[i].lower():
                return False

        def normalize_rows(rows):
            return sorted([tuple(str(val) for val in row) for row in rows])

        gen_normalized = normalize_rows(gen_results)
        exp_normalized = normalize_rows(exp_results)

        return gen_normalized == exp_normalized

    def _get_column_name_check_flags(self, exp_sql: str, gen_sql: str) -> list[bool]:
        """
        生成每一列是否需要检查列名的标记。

        维度列需要检查列名；聚合/计算指标列的别名可能由模型自动生成，
        只比较执行结果值即可。
        """
        exp_items = self._extract_select_items(exp_sql)
        gen_items = self._extract_select_items(gen_sql)

        if len(exp_items) != len(gen_items):
            return []

        flags = []
        for exp_item, gen_item in zip(exp_items, gen_items):
            should_check = (
                self._should_check_select_item_column_name(exp_item) or
                self._should_check_select_item_column_name(gen_item)
            )
            flags.append(should_check)
        return flags

    def _extract_select_items(self, sql: str) -> list[str]:
        """提取 SELECT 子句中的每一个输出项。"""
        if not sql:
            return []

        match = re.search(r'SELECT\s+(.*?)(?:\s+FROM\s+)', sql, re.IGNORECASE | re.DOTALL)
        if not match:
            return []

        select_clause = match.group(1).strip()

        items = []
        depth = 0
        current = []
        for char in select_clause:
            if char == '(':
                depth += 1
                current.append(char)
            elif char == ')':
                depth -= 1
                current.append(char)
            elif char == ',' and depth == 0:
                items.append(''.join(current).strip())
                current = []
            else:
                current.append(char)
        if current:
            items.append(''.join(current).strip())

        return items

    def _should_check_select_item_column_name(self, select_item: str) -> bool:
        """
        判断单个 SELECT 输出项是否需要检查列名。

        聚合/计算指标列通常由模型自动生成别名，语义等价时不强制匹配列名；
        普通维度列仍然检查列名，避免 product_line、region 等维度错位。
        """
        if not select_item:
            return True

        # 去除 AS 别名，避免别名影响判断。
        item_clean = re.split(r'\s+AS\s+', select_item, maxsplit=1, flags=re.IGNORECASE)[0].strip()

        # 只要 SELECT 项中包含聚合函数，就认为它是指标列。
        if re.search(r'\b(?:COUNT|SUM|AVG|MAX|MIN)\s*\(', item_clean, re.IGNORECASE):
            return False

        # 常量列也不强制检查列名。
        if re.match(r'^[\d+\-]?[\d]*\.?[\d]*$', item_clean):
            return False
        if re.match(r'^\'[^\']*\'$', item_clean) or re.match(r'^"[^"]*"$', item_clean):
            return False

        return True


def run_evaluation(
    sql_generator: Callable[[str], str],
    test_cases_path: str = "test_cases.json"
) -> None:
    """
    运行完整评估流程并打印报告

    Args:
        sql_generator: SQL 生成函数
        test_cases_path: 测试用例文件路径
    """
    evaluator = Evaluator()
    cases = evaluator.load_test_cases(test_cases_path)
    results = evaluator.evaluate_all(cases, sql_generator)
    print(evaluator.generate_report(results))


if __name__ == "__main__":
    # 示例：使用系统默认方式生成 SQL 进行自测
    import sys
    from prompt_builder import build_prompt
    from llm_client import LLMClient

    llm = LLMClient()

    def generate_sql(question: str) -> str:
        system_msg, prompt = build_prompt(question, use_rules=True, use_guards=True)
        return llm.generate_sql(system_msg, prompt)

    path = sys.argv[1] if len(sys.argv) > 1 else "test_cases.json"
    run_evaluation(generate_sql, path)
