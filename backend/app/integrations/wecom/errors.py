class WeComAPIError(Exception):
    def __init__(self, errcode: int, errmsg: str):
        super().__init__(f"wecom api error {errcode}: {errmsg}")
        self.errcode = errcode
        self.errmsg = errmsg
