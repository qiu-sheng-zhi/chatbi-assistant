# 简单验证，后面改为Query改写
class QueryParser:
    def parse(self, query: str):
        """
        判断用户问题是否有效，判断标准如下：
            - 输入是否为空
            - 输入是否仅为空格，换行，数字，字母，下划线
        :param query:
        :return:
        """
        is_valid = True
        if query.strip() == "":
            is_valid = False
        elif not query.replace(" ", "").replace("\n","").replace("\r", "").replace("\t", "").replace("_", "").isalnum():
            is_valid = False
        else:
            is_valid = True

        return is_valid

