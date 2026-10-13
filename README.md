# URL Content Reader

独立链接内容读取工具，保留宿主原有实现：读取用户提供的 HTTP(S) URL，提取标题、描述、正文、链接与跳转后的 URL，输出 HTML 和结构化 JSON。运行时仅依赖 Python 标准库，建议 Python 3.11+；不需要 Kimi 或 API key。

## 使用

```bash
python app/skills/external-search/scripts/url_content_reader.py \
  --url https://example.com/article --question "总结这篇文章" \
  --max-chars 12000 --output outputs/article.html \
  --payload-output outputs/article.json
```

`--url` 可重复；`--data` 支持 URL 字符串、JSON 字符串或数组。只读取 HTTP(S) 链接，单次最多处理前 8 个 URL；`--timeout` 默认为 20 秒，`--max-chars` 默认 12000、最少 1000。HTTP 响应读取上限沿用原实现的 5 MB，文字过长时记录 `truncated`。重定向后的 URL 用于解析相对链接。

`--output` 保存 HTML，`--payload-output` 保存 JSON；兼容的 `--format json` 不改变 HTML 输出约定。payload 保留 `type/query/urls/results/errors/article_count/sources`。单个链接失败会记录错误并继续读取其他链接；没有合法 URL 时直接报错。

这是内容提取器，不搜索新网页，也不直接生成大模型摘要。需要总结时，由宿主根据提取的文本回答。动态页面、登录内容、PDF 和非文本二进制内容不保证能提取；现有 HTTP/HTML 行为保持不变。

## 项目引用

宿主用 `url-content-reader.lock.json` 固定完整提交，将原入口 `app/skills/external-search/scripts/url_content_reader.py` 链接到 `.dependencies/url-content-reader` 的实现。Kimi 搜索和 external-search 路由继续独立维护。仓库不包含宿主应用、本地配置、密钥或用户输出。

## 测试

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

离线测试使用模拟网页和 HTTP 响应，不访问用户链接。
