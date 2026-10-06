"""Stable failure codes for acquisition, environment and parsing; never treat emptiness as success."""
import urllib.error


class SourceFailure(ValueError):
    def __init__(self,code,message,detected_tables=None,next_action='人工/OCR/视觉核对'):
        super().__init__(message);self.code=code;self.detected_tables=detected_tables;self.next_action=next_action


def classify(exc):
    if isinstance(exc,SourceFailure):
        return {'code':exc.code,'category':'eligibility' if exc.code=='OBSERVATION_OUT_OF_SCOPE' else 'parse','retryable':False,'reason':str(exc),'detected_tables':exc.detected_tables,'next_action':exc.next_action}
    if isinstance(exc,urllib.error.HTTPError):
        return {'code':'HTTP_ERROR','category':'network','retryable':exc.code in (408,429,500,502,503,504),'http_status':exc.code,'reason':str(exc),'next_action':'有界重试或更换官方入口；不要无限重试'}
    if isinstance(exc,(urllib.error.URLError,TimeoutError,ConnectionError)):
        return {'code':'NETWORK_ERROR','category':'network','retryable':True,'reason':str(exc),'next_action':'有界重试'}
    if isinstance(exc,(ImportError,ModuleNotFoundError)) or (isinstance(exc,RuntimeError) and any(k in str(exc).lower() for k in ('requires','unavailable','not installed','no chinese ocr backend'))):
        return {'code':'BACKEND_UNAVAILABLE','category':'environment','retryable':False,'reason':str(exc),'next_action':'运行 doctor.py / bootstrap.py 配置所需后端'}
    return {'code':'PARSING_OR_CONFIGURATION_ERROR','category':'parse','retryable':False,'reason':str(exc),'next_action':'核对文件格式、编码、映射或使用 OCR/视觉后端'}
