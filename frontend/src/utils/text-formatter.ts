/**
 * 文本格式化工具函数
 */

/**
 * 处理转义换行符，将 \n 转换为真正的换行符
 * 用于解决前端渲染 JSON 中转义换行符的问题
 * @param text 包含转义换行符的文本
 * @returns 格式化后的文本
 */
export function formatTextWithLineBreaks(text: string): string {
  if (!text || typeof text !== 'string') {
    return text || ''
  }
  
  // 将转义的 \n 转换为真正的换行符
  return text.replace(/\\n/g, '\n')
}

/**
 * 安全处理可能包含换行符的文本
 * 确保文本能正确渲染换行
 * @param text 可能包含转义换行符的文本
 * @param fallback 当文本为空时的默认值
 * @returns 安全的格式化文本
 */
export function safeFormatText(text: string | null | undefined, fallback: string = '待补充'): string {
  if (!text) {
    return fallback
  }
  
  return formatTextWithLineBreaks(text)
}

/**
 * 清理版本内容，处理转义字符和JSON解析
 * 用于处理章节版本内容的显示
 * @param content 版本内容字符串
 * @returns 清理后的版本内容
 */
export function cleanVersionContent(content: string): string {
  if (!content) return ''
  try {
    const parsed = JSON.parse(content)
    if (parsed && typeof parsed === 'object' && parsed.content) {
      content = parsed.content
    }
  } catch (error) {
    // not a json
  }
  let cleaned = content.replace(/^"|"$/g, '')
  cleaned = cleaned.replace(/\\n/g, '\n')
  cleaned = cleaned.replace(/\\"/g, '"')
  cleaned = cleaned.replace(/\\t/g, '\t')
  cleaned = cleaned.replace(/\\\\/g, '\\')
  return cleaned
}