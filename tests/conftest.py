"""必须在导入 app.crypto.kdf 之前设置，让全部测试使用轻量 KDF 参数。"""
import os

os.environ["SAFENOTES_LOW_KDF"] = "1"
