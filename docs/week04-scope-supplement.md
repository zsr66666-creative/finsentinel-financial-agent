# 四条口径证据向量补齐包

本地已生成真实 BAAI/bge-small-zh-v1.5 向量，固定 revision 7999e1d3359715c523056ef9478215996d62a620，512 维。PDF SHA256 为 841a3271cddd0e0e6bf9d60e39bda69fa48de13c67300c313395d849bddfa588。

私有包：`outputs/vector-batch/scope4.json`；SHA256：`461c0494eadbf796e7969f94da55b6a5036f72118bb7be1b05e2fc01587365e2`。不提交原文或向量包到公开仓库。

包含 p60-s8 合并标题、p60-s20 合并应收账款、p63-s4 母公司应收账款，以及新增 p62-fulltext-line117 母公司标题。新增 ID 明确采用完整页文本行命名；不是伪造旧 span。来源字段保留 PDF 哈希、文本哈希、物理页、提取方式和 scope_evidence_id。现有 span 原文与完整 PDF 规范空白后匹配。

## 服务器操作

上传私有包到 `/root/scope4.json` 后，在服务器运行下列命令；任一步失败则停止。

```bash
cd /opt/finsentinel
git pull --ff-only origin main
install -o finsentinel -g finsentinel -m 600 /root/scope4.json /var/tmp/finsentinel-scope4.json
sudo -u finsentinel env PYTHONPATH=/opt/finsentinel/backend:/opt/finsentinel DATABASE_URL='postgresql+psycopg:///finsentinel?host=/var/run/postgresql' /opt/finsentinel/.venv/bin/python -m scripts.vector_batch import --file /var/tmp/finsentinel-scope4.json --sha256 461c0494eadbf796e7969f94da55b6a5036f72118bb7be1b05e2fc01587365e2
# 再执行同一导入，检查 added=0
sudo -u finsentinel env PYTHONPATH=/opt/finsentinel/backend:/opt/finsentinel DATABASE_URL='postgresql+psycopg:///finsentinel?host=/var/run/postgresql' /opt/finsentinel/.venv/bin/python -m scripts.vector_batch import --file /var/tmp/finsentinel-scope4.json --sha256 461c0494eadbf796e7969f94da55b6a5036f72118bb7be1b05e2fc01587365e2
sudo -u finsentinel env PYTHONPATH=/opt/finsentinel/backend:/opt/finsentinel DATABASE_URL='postgresql+psycopg:///finsentinel?host=/var/run/postgresql' /opt/finsentinel/.venv/bin/python -m scripts.scope_supplement verify --file /var/tmp/finsentinel-scope4.json --sha256 461c0494eadbf796e7969f94da55b6a5036f72118bb7be1b05e2fc01587365e2
```

最后一步只读事务核对四条全部 provenance、模型、维数、文本哈希及逐元素向量误差 ≤1e-6。若初始十条与补齐包没有重叠且无其他写入，预期首次 added=4、after=14；第二次 added=0。若标题已存在，首次新增可以少于四条，仍须四条读回全部通过。

当前状态：本地生成与校验完成；未上传、未在阿里云运行导入或读回，远端幂等性验收仍 pending。不改变线上 API 或重启网站。不证明已完成在线向量问答。

