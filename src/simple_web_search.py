"""
简单的Web搜索工具
输入query，返回搜索结果
"""

import requests
import json
from typing import Dict, List, Optional
import time


def web_search(query: str, engine: str = "duckduckgo", max_results: int = 5) -> Dict:
    """
    执行网页搜索
    
    Args:
        query: 搜索关键词
        engine: 搜索引擎，支持 "duckduckgo", "google", "bing"
        max_results: 最大返回结果数
        
    Returns:
        包含搜索结果的字典
    """
    # 搜索引擎URL映射
    engine_urls = {
        "duckduckgo": "https://duckduckgo.com/html/",
        "google": "https://www.google.com/search",
        "bing": "https://www.bing.com/search"
    }
    
    if engine not in engine_urls:
        return {
            "error": f"不支持的搜索引擎: {engine}",
            "supported_engines": list(engine_urls.keys())
        }
    
    # 请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    
    # 请求参数
    params = {"q": query}
    
    try:
        print(f"正在搜索: {query} (使用: {engine})")
        
        # 发送请求
        response = requests.get(
            engine_urls[engine],
            params=params,
            headers=headers,
            timeout=10
        )
        
        # 检查响应状态
        response.raise_for_status()
        
        # 返回原始数据
        return {
            "query": query,
            "engine": engine,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type", "unknown"),
            "content_length": len(response.text),
            "raw_html_preview": response.text[:1000] + "..." if len(response.text) > 1000 else response.text,
            "full_html_available": True,
            "timestamp": time.time(),
            "success": True
        }
        
    except requests.exceptions.RequestException as e:
        return {
            "query": query,
            "engine": engine,
            "error": str(e),
            "success": False,
            "timestamp": time.time()
        }
    except Exception as e:
        return {
            "query": query,
            "engine": engine,
            "error": f"未知错误: {str(e)}",
            "success": False,
            "timestamp": time.time()
        }


def search_and_save(query: str, filename: str = "search_result.json") -> Dict:
    """
    执行搜索并保存结果到文件
    
    Args:
        query: 搜索关键词
        filename: 保存结果的文件名
        
    Returns:
        搜索结果字典
    """
    result = web_search(query)
    
    # 保存到文件
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"结果已保存到: {filename}")
    except Exception as e:
        print(f"保存文件失败: {e}")
    
    return result


# 使用示例
if __name__ == "__main__":
    print("=== Web搜索工具演示 ===")
    
    # 示例1: 基本搜索
    print("\n1. 基本搜索演示:")
    result1 = web_search("Python编程教程")
    print(f"查询: {result1.get('query')}")
    print(f"引擎: {result1.get('engine')}")
    print(f"状态码: {result1.get('status_code')}")
    print(f"内容长度: {result1.get('content_length')} 字符")
    
    # 示例2: 使用不同搜索引擎
    print("\n2. 不同搜索引擎演示:")
    engines = ["duckduckgo", "google", "bing"]
    for engine in engines:
        result = web_search("人工智能", engine=engine, max_results=2)
        print(f"{engine}: {'成功' if result.get('success') else '失败'} - {result.get('content_length', 0)} 字符")
    
    # 示例3: 搜索并保存
    print("\n3. 搜索并保存演示:")
    search_result = search_and_save("昨天的valorant的cn赛区的比赛结果", "valorant_search.json")
    
    if search_result.get("success"):
        print("搜索成功！")
        print(f"原始HTML预览: {search_result.get('raw_html_preview', '')[:200]}...")
    else:
        print(f"搜索失败: {search_result.get('error')}")
    
    print("\n=== 函数使用说明 ===")
    print("""
使用方式:
1. 导入函数:
   from simple_web_search import web_search, search_and_save
    
2. 基本搜索:
   result = web_search("搜索关键词")
    
3. 指定搜索引擎:
   result = web_search("关键词", engine="google")
    
4. 搜索并保存:
   result = search_and_save("关键词", "output.json")
    """)