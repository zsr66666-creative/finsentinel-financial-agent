# Task 8 CPU 可行性评估（尚未上线）

用户选择先评估现有 ECS 的轻量 CPU 方案，不增加第三方服务。

固定 BAAI/bge-small-zh-v1.5 修订 7999e1d3359715c523056ef9478215996d62a620，保留原 tokenizer、中文查询前缀、512 token 截断、CLS 池化和 L2 归一化。本地从原始权重导出 FP32 ONNX，不进行量化，不替换模型空间。模型与查询向量留在忽略的 outputs 中，不提交公开仓库。

2026-11-15 Windows CPU 独立进程实测：ONNX 90.45 MiB；初始化约177.7 ms；进程RSS227.3 MiB、峰值232.5 MiB；4个短问题各4轮约8.5–15.2 ms；512-token长输入4轮约143.7–150.3 ms。5组输入均与原 sentence-transformers 结果最大分量误差小于2e-7，余弦相似度约1；报告 imported_torch=false。详细结果 data/evals/task8-local-cpu-assessment.json。

边界：没有云端 Linux 内存/延迟或并发实测，没有部署新接口或网页输入框。Windows进程工作集不等于Linux RSS；峰值包括本次采样前所有推理，但不含随后读取模型文件计算哈希的缓冲。小规模对照不是所有输入上的形式等价证明。

建议：采用独立 ONNX Runtime 单进程、单线程服务，仅监听127.0.0.1；后端通过有界超时调用，限制同时推理数量和问题长度，错误时明确失败不生成假向量。避免在每个API worker复制模型。上线前检查 MemAvailable、原服务峰值和swap，云端独立评测后才切换网页。暂不在ECS安装PyTorch。

本地复现：python -m scripts.task8_cpu_assessment export（需缓存原模型、torch、sentence-transformers、onnx）；另起进程 python -m scripts.task8_cpu_assessment benchmark（需onnxruntime、tokenizers、numpy、psutil）。
