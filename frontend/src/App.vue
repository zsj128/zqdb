<template>
  <div class="app-container">
    <!-- 顶部导航 -->
    <header class="header">
      <div class="header-inner">
        <div class="logo">
          <el-icon :size="28" color="#1a56db"><Scale /></el-icon>
          <h1>智能法律咨询助手</h1>
        </div>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="main-content">
      <el-tabs v-model="activeTab" class="main-tabs">

        <!-- Tab 1: 法条搜索 -->
        <el-tab-pane label="📜 法律条文搜索" name="search">
          <div class="search-panel">
            <div class="search-bar">
              <el-input v-model="searchQuery" size="large"
                placeholder="输入关键词搜索法律条文（如：盗窃、劳动合同...）"
                @keyup.enter="handleSearch" clearable>
                <template #prefix><el-icon><Search /></el-icon></template>
                <template #append>
                  <el-button type="primary" @click="handleSearch" :loading="searching">检索法条</el-button>
                </template>
              </el-input>
            </div>

            <div v-if="searchResults.length > 0" class="results-list">
              <el-card v-for="(item, idx) in searchResults" :key="idx" class="result-card" shadow="hover">
                <div class="result-header">
                  <el-tag v-if="item.article_key" type="danger" size="small" effect="dark">{{ item.article_key }}</el-tag>
                  <el-tag v-else-if="item.articles" type="danger" size="small" effect="dark">{{ item.articles }}</el-tag>
                </div>
                <div class="result-body">{{ item.article_content || item.text }}</div>
              </el-card>
            </div>
            <el-empty v-else-if="hasSearched && !searching && searchQuery" description="未找到相关法条" />
          </div>
        </el-tab-pane>

        <!-- Tab 2: AI 法律问答 -->
        <el-tab-pane label="🤖 AI 问答" name="chat">
          <div class="chat-panel">
            <div class="chat-messages" ref="chatMessagesRef">
              <div v-if="messages.length === 0" class="chat-welcome">
                <el-icon :size="64" color="#c0c4cc"><ChatDotRound /></el-icon>
                <h3>智能法律咨询助手</h3>
                <p>我可以帮您查询法律条文、分析法律问题、提供初步法律建议</p>
                <div class="quick-questions">
                  <el-button v-for="q in quickQuestions" :key="q" size="small" round @click="askQuick(q)">{{ q }}</el-button>
                </div>
              </div>

              <div v-for="(msg, idx) in messages" :key="idx" :class="['message', msg.role]">
                <div class="message-avatar">
                  <el-icon v-if="msg.role === 'user'" :size="24"><User /></el-icon>
                  <el-icon v-else :size="24"><Bot /></el-icon>
                </div>
                <div class="message-content">
                  <!-- 回答正文 + 法律分析（可折叠） -->
                  <template v-if="parsedAnswer(msg.content)">
                    <div class="message-text" v-html="formatAnswer(parsedAnswer(msg.content).main)"></div>
                    <div v-if="parsedAnswer(msg.content).analysis" class="message-analysis">
                      <el-collapse>
                        <el-collapse-item name="analysis">
                          <template #title>
                            <span class="analysis-title">🔍 法律分析过程</span>
                          </template>
                          <div class="analysis-body" v-html="formatAnswer(parsedAnswer(msg.content).analysis)"></div>
                        </el-collapse-item>
                      </el-collapse>
                    </div>
                  </template>
                  <div v-else class="message-text" v-html="formatAnswer(msg.content)"></div>
                  <!-- 引用来源（可折叠） -->
                  <div v-if="msg.sources?.length" class="message-sources">
                    <el-collapse>
                      <el-collapse-item name="sources">
                        <template #title>
                          <span class="source-title">📎 最相关的 {{ msg.sources.length }} 条引用来源</span>
                        </template>
                        <div v-for="(src, si) in msg.sources" :key="si" class="source-item-collapsed">
                          <div class="source-row">
                            <el-tag v-if="src.source_type === 'sample' && src.source_file" type="danger" size="small" effect="dark">{{ src.source_file.replace('.pdf', '') }}</el-tag>
                            <el-tag v-else-if="src.article_key" type="danger" size="small">{{ src.article_key }}</el-tag>
                            <el-tag v-else-if="src.articles" type="danger" size="small">{{ src.articles }}</el-tag>
                          </div>
                          <div v-if="src.source_type !== 'sample'" class="source-text">{{ src.article_content || src.text }}</div>
                        </div>
                      </el-collapse-item>
                    </el-collapse>
                  </div>
                </div>
              </div>

              <div v-if="chatLoading" class="message assistant">
                <div class="message-avatar"><el-icon :size="24"><Bot /></el-icon></div>
                <div class="message-content"><el-skeleton :rows="4" animated /></div>
              </div>
            </div>

            <div class="chat-input-area">
              <el-input v-model="chatInput" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
                placeholder="请描述您的法律问题..." @keyup.ctrl.enter="handleChat" :disabled="chatLoading" />
              <el-button type="primary" @click="handleChat" :loading="chatLoading" :disabled="!chatInput.trim()">
                发送 (Ctrl+Enter)
              </el-button>
            </div>
          </div>
        </el-tab-pane>

        <!-- Tab 3: 知识库管理 -->
        <el-tab-pane label="📚 知识库管理" name="manage">
          <div class="manage-panel">
            <el-divider content-position="left">LLM 配置</el-divider>
            <el-form label-width="100px" style="max-width: 600px;">
              <el-form-item label="API Key">
                <el-input v-model="apiKey" type="password" placeholder="请输入 API Key" show-password style="width: 400px;" />
                <span style="font-size: 12px; color: #909399; margin-left: 10px;">支持千问 / OpenAI 兼容接口</span>
              </el-form-item>
              <el-form-item label="模型名称">
                <el-input v-model="modelName" placeholder="如: qwen-plus / gpt-4o / deepseek-chat" style="width: 300px;" />
              </el-form-item>
              <el-form-item label="Base URL（可选）">
                <el-input v-model="baseUrl" placeholder="留空使用千问默认地址" style="width: 400px;" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="saveLlmConfig">保存配置</el-button>
                <el-tag :type="llmSaved ? 'success' : 'info'" size="small">{{ llmSaved ? '已保存' : '未配置' }}</el-tag>
              </el-form-item>
            </el-form>

            <el-divider />

            <h3>📜 法律知识库</h3>
            <el-alert v-if="fileList.law.length === 0" title="法律知识库暂无数据" type="warning"
              :closable="false" show-icon style="margin-bottom: 12px;" />
            <el-table v-else :data="fileList.law" size="small" border stripe style="margin-bottom: 16px;">
              <el-table-column prop="filename" label="文件名" />
              <el-table-column label="状态" width="100" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.imported ? 'success' : 'warning'" size="small">{{ row.imported ? '已导入' : '待导入' }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="120" align="center">
                <template #default="{ row }">
                  <el-button size="small" @click="importFile(row.full_path, 'sample')" :disabled="row.imported || rebuilding">
                    {{ row.imported ? '已导入' : '导入' }}
                  </el-button>
                </template>
              </el-table-column>
            </el-table>

            <h3>📋 案例知识库</h3>
            <el-alert v-if="fileList.sample.length === 0"
              title="案例知识库暂无数据"
              type="warning" :closable="false" show-icon style="margin-bottom: 12px;" />
            <el-table v-else :data="fileList.sample" size="small" border stripe style="margin-bottom: 16px;">
              <el-table-column prop="filename" label="文件名" />
              <el-table-column label="状态" width="100" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.imported ? 'success' : 'warning'" size="small">{{ row.imported ? '已导入' : '待导入' }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="120" align="center">
                <template #default="{ row }">
                  <el-button size="small" @click="importFile(row.full_path, 'sample')" :disabled="row.imported || rebuilding">
                    {{ row.imported ? '已导入' : '导入' }}
                  </el-button>
                </template>
              </el-table-column>
            </el-table>

            <el-divider content-position="left">手动导入</el-divider>
            <el-form inline>
              <el-form-item label="文件绝对路径">
                <el-input v-model="newPdfNameLaw" placeholder="如: D:\Code\zqdb\data\law\民法典.docx" style="width: 400px;" />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="handleRebuild('law')" :loading="rebuilding">导入到法律知识库</el-button>
              </el-form-item>
            </el-form>
            <el-form inline style="margin-top: 8px;">
              <el-form-item label="文件绝对路径">
                <el-input v-model="newPdfNameSample" placeholder="如: D:\Code\zqdb\data\sample\案例.docx" style="width: 400px;" />
              </el-form-item>
              <el-form-item>
                <el-button type="success" @click="handleRebuild('sample')" :loading="rebuilding">导入到案例知识库</el-button>
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>

      </el-tabs>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 30000 })

// 状态
const activeTab = ref('search')
const stats = ref({ total_chunks: 0, bm25_ready: false, embedding_model: '', llm: '', law_chunks: 0, sample_chunks: 0 })
const searchQuery = ref('')
const searchResults = ref([])
const searching = ref(false)
const hasSearched = ref(false)
const chatInput = ref('')
const messages = ref([])
const chatLoading = ref(false)
const chatMessagesRef = ref(null)
const newPdfNameLaw = ref('')
const newPdfNameSample = ref('')
const rebuilding = ref(false)
const fileList = ref({ law: [], sample: [] })
// LLM 配置
const apiKey = ref(localStorage.getItem('llm_api_key') || '')
const modelName = ref(localStorage.getItem('llm_model_name') || 'qwen-plus')
const baseUrl = ref(localStorage.getItem('llm_base_url') || '')
const llmSaved = ref(!!apiKey.value)
const quickQuestions = ['盗窃罪怎么判刑？', '劳动合同解除需要什么条件？', '交通事故责任如何划分？']

// 方法
async function fetchStats() { try { const r = await api.get('/stats'); stats.value = r.data } catch(e) {} }
async function fetchFiles() { try { const r = await api.get('/files'); fileList.value = r.data } catch(e) {} }

async function handleSearch() {
  if (!searchQuery.value.trim()) return
  hasSearched.value = true
  searching.value = true
  try {
    const res = await api.post('/search', { query: searchQuery.value, n_results: 8 })
    searchResults.value = res.data.results
  } catch (e) { searchResults.value = [] }
  finally { searching.value = false }
}

function askQuick(q) { chatInput.value = q; handleChat() }

async function handleChat() {
  const question = chatInput.value.trim()
  if (!question || chatLoading.value) return
  messages.value.push({ role: 'user', content: question })
  chatInput.value = ''
  chatLoading.value = true
  scrollToBottom()
  try {
    const res = await api.post('/chat', { question, n_results: 5,
      api_key: apiKey.value || '',
      model: modelName.value || 'qwen-plus',
      base_url: baseUrl.value || '',
    })
    messages.value.push({ role: 'assistant', content: res.data.answer, sources: res.data.sources })
  } catch (e) {
    messages.value.push({ role: 'assistant', content: `⚠ 请求失败: ${e.message}` })
  } finally {
    chatLoading.value = false; scrollToBottom()
  }
}

async function handleRebuild(sourceType) {
  const pdfPath = sourceType === 'law' ? newPdfNameLaw.value.trim() : newPdfNameSample.value.trim()
  if (!pdfPath) return
  rebuilding.value = true
  try {
    const res = await api.post('/rebuild', { pdf_path: pdfPath, source_type: sourceType })
    alert(`✅ ${res.data.message}`)
    newPdfNameLaw.value = ''
    newPdfNameSample.value = ''
    fetchStats(); fetchFiles()
  } catch (e) { alert(`❌ 失败: ${e.response?.data?.detail || e.message}`) }
  finally { rebuilding.value = false }
}

async function importFile(fullPath, sourceType) {
  if (!confirm(`确定导入\n${fullPath}？`)) return
  if (sourceType === 'law') newPdfNameLaw.value = fullPath
  else newPdfNameSample.value = fullPath
  await handleRebuild(sourceType)
}

function saveLlmConfig() {
  localStorage.setItem('llm_api_key', apiKey.value)
  localStorage.setItem('llm_model_name', modelName.value)
  localStorage.setItem('llm_base_url', baseUrl.value)
  llmSaved.value = true
}

function parsedAnswer(text) {
  if (!text) return null
  const idx = text.indexOf('【法律分析】')
  if (idx === -1) return { main: text, analysis: '' }
  let main = text.substring(0, idx).trim()
  let analysis = text.substring(idx).trim()
  // 将结论部分从分析中提取到正文
  let conclusion = ''
  const cIdx = analysis.search(/[-–—·]\s*最后得出结论[：:]|【结论】/)
  if (cIdx !== -1) {
    conclusion = analysis.substring(cIdx).trim()
      .replace(/^[-–—·]\s*最后得出结论[：:]\s*/, '')
      .replace(/^【结论】\s*/, '')
    analysis = analysis.substring(0, cIdx).trim()
  }
  // 清理正文中的格式标记
  main = main
    .replace(/^第一部分[：:].*/m, '')       // 去掉"第一部分："整行
    .replace(/^第二部分[：:].*/m, '')
    .replace(/^[－\-·]\s*直接给出答案.*$/m, '')  // 去掉结论说明行
    .replace(/\n*【结论】\s*/g, '')
    .trim()
  return { main: conclusion ? (main + '\n\n' + conclusion) : main, analysis }
}

function formatAnswer(text) {
  if (!text) return ''
  return text
    .replace(/&nbsp;/g, ' ')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/【引用：(.*?)】/g, '<span class="law-ref">【引用：$1】</span>')
}

function scrollToBottom() {
  nextTick(() => { if (chatMessagesRef.value) chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight })
}

onMounted(() => { fetchStats(); fetchFiles() })
</script>

<style scoped>
.app-container { min-height: 100vh; display: flex; flex-direction: column; }

.header { background: linear-gradient(135deg, #1a56db, #2e6ee5); color: white; padding: 12px 24px; box-shadow: 0 2px 8px rgba(0,0,0,.15); }
.header-inner { max-width: 1200px; margin: 0 auto; display: flex; align-items: center; gap: 20px; }
.logo { display: flex; align-items: center; gap: 10px; }
.logo h1 { font-size: 20px; font-weight: 600; margin: 0; }
.header-stats { margin-left: auto; display: flex; align-items: center; gap: 8px; font-size: 14px; }

.main-content { flex: 1; max-width: 1200px; width: 100%; margin: 0 auto; padding: 20px; }
.main-tabs { background: #fff; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }

.search-panel { padding: 10px 0; }
.search-bar { max-width: 800px; margin-bottom: 12px; }
.result-card { margin-bottom: 12px; border-left: 3px solid #1a56db; }
.result-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.result-meta { font-size: 13px; color: #6b7280; }
.result-body { font-size: 14px; line-height: 1.8; white-space: pre-wrap; word-break: break-all; color: #374151; }

.chat-panel { display: flex; flex-direction: column; height: calc(80vh - 40px); }
.chat-messages { flex: 1; overflow-y: auto; padding: 16px 0; border: 1px solid #e5e7eb; border-radius: 8px; background: #fafbfc; }
.chat-welcome { text-align: center; padding: 60px 20px; color: #9ca3af; }
.chat-welcome h3 { color: #374151; margin: 16px 0 8px; }
.quick-questions { display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; }

.message { display: flex; gap: 12px; margin-bottom: 20px; padding: 0 16px; }
.message.user { flex-direction: row-reverse; }
.message-avatar { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex-shrink: 0; background: #dbeafe; }
.message.user .message-avatar { background: #bfdbfe; }
.message-content { max-width: 75%; padding: 12px 16px; border-radius: 12px; line-height: 1.7; font-size: 14px; }
.message.user .message-content { background: #1a56db; color: white; border-radius: 12px 12px 0 12px; }
.message.assistant .message-content { background: white; border: 1px solid #e5e7eb; border-radius: 12px 12px 12px 0; }
.message-text { word-break: break-word; }
.law-ref { color: #dc2626; font-weight: 600; background: #fef2f2; padding: 1px 4px; border-radius: 3px; }

.message-sources { margin-top: 10px; }
.source-title { font-size: 13px; color: #6b7280; }
.source-item-collapsed { margin-bottom: 8px; padding: 6px 10px; background: #f9fafb; border-radius: 6px; }
.source-row { display: flex; align-items: flex-start; gap: 8px; font-size: 13px; color: #6b7280; flex-wrap: wrap; }
.source-text { margin-top: 6px; font-size: 13px; color: #374151; line-height: 1.8; white-space: pre-wrap; word-break: break-all; background: #f9fafb; padding: 8px; border-radius: 6px; }

.message-analysis { margin-top: 8px; }
.analysis-title { font-size: 13px; color: #1a56db; font-weight: 500; }
.analysis-body { font-size: 13px; color: #4b5563; line-height: 1.8; word-break: break-all; background: #eff6ff; padding: 10px 12px; border-radius: 6px; }

.chat-input-area { display: flex; gap: 12px; align-items: flex-end; }
.chat-input-area .el-input { flex: 1; }

.manage-panel { padding: 10px 0; }
.manage-panel h3 { font-size: 15px; color: #374151; margin-bottom: 10px; }
</style>
