"""Free seller tools (utility tier).

算数/规则类工具为纯本地公式计算，零边际成本；内容类工具复用已购 MiniMax
年包（AGENT_ANTHROPIC），并带配额保护（输入长度上限、单 IP 限流、结果缓存、
每日调用上限），接近配额或调用失败时降级为"复制提示词跳转智能体"。
"""
