import streamlit as st
from docx import Document
import os
import asyncio
import io
import json
import requests  # 引入 requests 库

# --- 全局变量 ---
# Vercel 函数的 URL
vercel_function_url = "https://ai-translate-gamma.vercel.app/api/translate"

# Streamlit 应用标题
st.title("Word 文档翻译")

# 文件上传
uploaded_file = st.file_uploader("上传 Word 文档 (.docx)", type=["docx"])

# 目标语言选择
target_language = st.selectbox("选择目标语言", ["zh-CN", "en", "ja", "ko", "fr", "de", "es"])

# 双语模式选择
bilingual = st.checkbox("双语对照模式", False)

# --- 翻译进度条 ---
progress_bar = st.progress(0, text="准备翻译...")
progress_lock = asyncio.Lock() 
total_elements = 0
completed_elements = 0


async def update_progress(completed):
    """更新进度条"""
    async with progress_lock:
        progress = int(completed)
        progress_bar.progress(progress, text=f"正在翻译... ({progress}%)")


async def translate_text(texts):
    """使用 Google Gemini API 批量翻译文本"""
    # 设置最大 token 限制
    max_tokens = 8000

    # 将文本列表分割成多个批次，每个批次的 token 数量不超过最大限制
    batches = []
    current_batch = []
    current_tokens = 0
    for i, text in enumerate(texts):
        text_tokens = len(text)
        if current_tokens + text_tokens > max_tokens:
            batches.append(current_batch)
            current_batch = []
            current_tokens = 0
        current_batch.append((i, text))
        current_tokens += text_tokens
    if current_batch:
        batches.append(current_batch)

# 并发地翻译每个批次
    async def translate_batch(batch, batch_index, total_batches):
        print(f"正在翻译第{batch_index}批。。。。。。")
        batch_start = int(batch_index * 100 / total_batches)
        await update_progress(int(batch_start + 0.2 * (100 / total_batches)))
        batch_prompt = ""
        for i, text in batch:
            batch_prompt += f"{i}. {text}\n"

        batch_translations = []
        
        request_data = {"texts": texts, "target_language": target_language}
        try:
            # 发送 POST 请求到 Vercel 函数
            response = requests.post(vercel_function_url, json=request_data)

            # 检查响应状态码
            response.raise_for_status()

            # 解析 JSON 响应
            batch_translations = response.json()
            await update_progress(int(batch_start + 0.9 * (100 / total_batches)))
            return batch_translations
        except requests.exceptions.RequestException as e:
            st.error(f"翻译时出错: {e}")
            st.exception(e)  # 显示完整的错误堆栈
            return []

    # 创建异步任务列表
    tasks = [
        translate_batch(batch, batch_index, len(batches))
        for batch_index, batch in enumerate(batches)
    ]

    # 并发执行所有任务
    results = await asyncio.gather(*tasks)

    # 合并所有翻译结果
    translations = []
    for result in results:
        translations.extend(result)

    translations.sort(key=lambda x: int(x['index']))  # 将 index 转换为整数
    return [t['translation'].rstrip() for t in translations]


async def process_paragraph(paragraph, translations, paragraph_index):
    """处理单个段落，包含翻译和进度更新"""
    run = paragraph.runs[0]
    for aRun in paragraph.runs:
        original_text = aRun.text.strip()
        if original_text:
            run = aRun
            break

    if bilingual:
        new_run = paragraph.add_run("\n"+translations[paragraph_index])
        if run:
            # 在 translations 中查找对应的翻译结果
            new_run.font.bold = run.font.bold
            new_run.font.italic = run.font.italic
            new_run.font.underline = run.font.underline
            new_run.font.color.rgb = run.font.color.rgb
    else:
        paragraph.text = translations[paragraph_index]
        if run:
           for new_run in paragraph.runs:
               new_run.font.bold = run.font.bold
               new_run.font.italic = run.font.italic
               new_run.font.underline = run.font.underline
               new_run.font.color.rgb = run.font.color.rgb

async def translate_document(document):
    """使用 asyncio 异步翻译文档"""
    global total_elements, completed_elements
    total_elements = 0
    texts_to_translate = []

    for paragraph in document.paragraphs:
        original_text = paragraph.text.strip()
        if original_text:
            texts_to_translate.append(paragraph.text)
            total_elements += 1

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    original_text = paragraph.text.strip()
                    if original_text:
                        texts_to_translate.append(paragraph.text)
                        total_elements += 1

    completed_elements = 0

    translations = await translate_text(texts_to_translate)

    # 检查 translations 是否为空
    if not translations:
        st.error("翻译结果为空！")
        st.exception(Exception("翻译结果为空"))  # 抛出异常并显示堆栈信息
        return

    tasks = []
    current_paragraph_index = 0
    for paragraph in document.paragraphs:
        original_text = paragraph.text.strip()
        if original_text:
            tasks.append(
                asyncio.create_task(
                    process_paragraph(paragraph, translations, current_paragraph_index)
                )
            )
            current_paragraph_index += 1

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    original_text = paragraph.text.strip()
                    if original_text:
                        tasks.append(
                            asyncio.create_task(
                                process_paragraph(paragraph, translations, current_paragraph_index)
                            )
                        )
                        current_paragraph_index += 1

    await asyncio.gather(*tasks)
    return document


# 翻译按钮
if st.button("开始翻译") and uploaded_file is not None:
    try:
        # 读取 Word 文档
        doc = Document(uploaded_file)

        # 使用 asyncio 运行异步函数
        translated_doc = asyncio.run(translate_document(doc))

        # 将翻译后的文档保存到内存中
        output = io.BytesIO()
        translated_doc.save(output)
        output.seek(0)

        # 提供下载链接
        st.download_button(
            label="下载翻译后的文档",
            data=output.getvalue(),
            file_name=f"translated_{uploaded_file.name}",
        )

    except Exception as e:
        st.error(f"翻译过程中出现错误：{e}")
        st.exception(e)  # 显示完整的错误堆栈