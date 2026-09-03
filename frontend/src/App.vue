<template>
  <div class="app-container">
    <!-- 顶部导航 -->
    <header class="header">
      <div class="header-inner">
        <div class="logo">
          <el-icon :size="28" color="#1a56db"><Scale /></el-icon>
          <h1>智能法律咨询助手</h1>
        </div>
        <div class="user-area">
          <template v-if="isLoggedIn">
            <span class="welcome-text">欢迎, {{ username }}</span>
            <el-button text style="color: white;" @click="logout">退出</el-button>
          </template>
        </div>
      </div>
    </header>

    <!-- 登录/注册弹窗 -->
    <el-dialog v-model="authVisible" :title="authMode === 'login' ? '用户登录' : '用户注册'"
      width="500px" :close-on-click-modal="false">
      <Login v-if="authMode === 'login'" @switch="showAuth" @login-success="onLoginSuccess" />
      <Register v-else @switch="showAuth" @register-success="onRegisterSuccess" />
    </el-dialog>

    <!-- 未登录时显示全屏登录页 -->
    <div v-if="!isLoggedIn" class="auth-page">
      <div class="auth-container">
        <div class="auth-logo">
          <el-icon :size="48" color="#1a56db"><Scale /></el-icon>
          <h1>智能法律咨询助手</h1>
        </div>
        <Login @switch="showAuth" @login-success="onLoginSuccess" />
      </div>
    </div>

    <!-- 主内容区（已登录才显示） -->
    <main v-else class="main-content">
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
              <div class="result-count">共检索到 <b>{{ searchResults.length }}</b> 条法条</div>
              <el-card v-for="(item, idx) in pagedResults" :key="idx" class="result-card" shadow="hover">
                <div class="result-header">
                  <el-tag v-if="item.article_key" type="danger" size="small" effect="dark">{{ item.article_key }}</el-tag>
                  <el-tag v-else-if="item.articles" type="danger" size="small" effect="dark">{{ item.articles }}</el-tag>
                </div>
                <div class="result-body">{{ item.article_content || item.text }}</div>
              </el-card>
            </div>
            <el-empty v-else-if="hasSearched && !searching && searchQuery" description="未找到相关法条" />

            <!-- 分页：每页 20 条 -->
            <div v-if="searchResults.length > PAGE_SIZE" class="pagination-wrap">
              <el-pagination
                background
                layout="total, prev, pager, next"
                :total="searchResults.length"
                :page-size="PAGE_SIZE"
                :current-page="searchPage"
                @current-change="searchPage = $event"
              />
            </div>
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
                  <!-- 流式输出中：直接显示累积原文，避免中途切换布局 -->
                  <template v-if="msg.streaming">
                    <div class="message-text" v-html="formatAnswer(msg.content)"></div>
                  </template>
                  <!-- 完成后的回答正文 + 法律分析（可折叠） -->
                  <template v-else-if="parsedAnswer(msg.content)">
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
                  <!-- 流式光标 -->
                  <span v-if="msg.streaming" class="stream-cursor"></span>
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
            </div>

            <!-- 附件选择栏（pdf/word/md/txt） -->
            <div v-if="attachedFile" class="chat-attachment-bar">
              <span class="chat-attachment-name">📎 {{ attachedFile.name }}</span>
              <el-button text size="small" type="danger" @click="removeChatFile" :disabled="chatLoading">移除</el-button>
            </div>
            <div class="chat-input-area">
              <el-input v-model="chatInput" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }"
                placeholder="请描述您的法律问题，或附带文件让 AI 参考后回答..." @keyup.ctrl.enter="handleChat" :disabled="chatLoading" />
              <div class="chat-buttons">
                <el-button @click="openChatFilePicker" :disabled="chatLoading" title="上传文件（pdf/word/md/txt）">
                  📎
                </el-button>
                <el-button type="primary" @click="handleChat" :loading="chatLoading"
                  :disabled="!chatInput.trim()">
                  发送 (Ctrl+Enter)
                </el-button>
              </div>
              <!-- 隐藏的文件选择器 -->
              <input ref="chatFileInputRef" type="file" :accept="ATTACHMENT_ACCEPT" hidden
                @change="onChatFileSelected" />
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

            <!-- 系统运行监控面板（参考 day64 可观测性） -->
            <el-card shadow="never" style="margin-bottom: 16px;">
              <template #header>
                <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
                  <b>📊 系统运行监控</b>
                  <el-button size="small" :loading="loadingMetrics" @click="fetchMetrics">刷新</el-button>
                  <span style="font-size:12px; color:rgba(255,255,255,0.4);">
                    请求数 / 缓存命中率 / 降级率 / 延迟分位数
                  </span>
                </div>
              </template>
              <div v-if="metrics" class="metrics-grid">
                <div class="metric-item">
                  <div class="metric-value">{{ metrics.total_requests }}</div>
                  <div class="metric-label">总请求数</div>
                </div>
                <div class="metric-item">
                  <div class="metric-value" :style="{ color: metrics.cache_hit_rate > 0.3 ? '#22c55e' : '#f59e0b' }">
                    {{ (metrics.cache_hit_rate * 100).toFixed(1) }}%
                  </div>
                  <div class="metric-label">缓存命中率</div>
                </div>
                <div class="metric-item">
                  <div class="metric-value" :style="{ color: metrics.error_rate > 0.2 ? '#ef4444' : '#22c55e' }">
                    {{ (metrics.error_rate * 100).toFixed(1) }}%
                  </div>
                  <div class="metric-label">降级率</div>
                </div>
              </div>
              <el-empty v-else-if="!loadingMetrics" description="暂无监控数据，刷新后查看" :image-size="50" />
              <!-- 熔断状态 -->
              <div v-if="circuitStats" class="circuit-status">
                <el-tag :type="circuitStats.state === 'OPEN' ? 'danger' : (circuitStats.state === 'HALF_OPEN' ? 'warning' : 'success')" size="small" effect="dark">
                  熔断器: {{ circuitStats.state }}
                </el-tag>
                <span style="font-size:12px; color:rgba(255,255,255,0.4); margin-left:8px;">
                  连续失败 {{ circuitStats.consecutive_failures }} / {{ circuitStats.threshold }}
                </span>
              </div>
            </el-card>

            <el-divider />

            <!-- 知识库中已加载的文件列表（用于确认加载是否成功） -->
            <el-card shadow="never" style="margin-bottom: 16px;">
              <template #header>
                <div style="display:flex; align-items:center; gap:12px; flex-wrap:wrap;">
                  <b>📦 我的知识库已加载文件</b>
                  <el-button size="small" :loading="loadingKbFiles" @click="fetchKbFiles">刷新</el-button>
                  <span v-if="!loadingKbFiles && !reloading" style="font-size:12px; color:#909399;">
                    共 {{ kbTotalFiles }} 个文件，{{ kbTotalChunks }} 条数据
                  </span>
                  <el-button size="small" type="danger" plain :loading="deletingUserData" @click="deleteMyLocalData" style="margin-left:auto;">
                    清空我的本地数据
                  </el-button>
                </div>
              </template>

              <!-- 数据加载中提示 -->
              <el-alert v-if="reloading" type="info" :closable="false" show-icon style="margin-bottom: 12px;">
                <template #title>
                  <span class="kb-loading-text">正在加载知识库数据，请稍候...</span>
                </template>
              </el-alert>
              <div v-else-if="loadingKbFiles" class="kb-loading-text" style="padding:16px 0; text-align:center; color:#909399;">
                正在刷新知识库文件列表...
              </div>

              <el-empty v-if="!loadingKbFiles && !reloading && kbFiles.length === 0"
                description="知识库暂无已加载文件，请在上方导入" :image-size="60" />
              <el-table v-else-if="!reloading" :data="kbFiles" size="small" border stripe :loading="loadingKbFiles">
                <el-table-column prop="filename" label="文件名" min-width="280" show-overflow-tooltip />
                <el-table-column prop="source_type" label="类型" width="100">
                  <template #default="{ row }">
                    <el-tag :type="row.source_type === 'law' ? 'danger' : 'success'" size="small">
                      {{ row.source_type === 'law' ? '法律' : '案例' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="chunks" label="已加载条数" width="120" align="center">
                  <template #default="{ row }">
                    <el-tag v-if="row.chunks > 0" type="success" size="small">✅ {{ row.chunks }} 条</el-tag>
                    <el-tag v-else type="danger" size="small">加载失败</el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </el-card>

            <!-- 知识数据导入总览 -->
            <h3>📚 数据导入</h3>
            <el-alert title="可手动向知识库添加数据：支持「一次插入一个文件夹里的所有文件」或「一次插入单个文件」，并分「法律文件」「法律案例」两个入口。插入的目录/文件地址会保存到您的账号，下次登录自动恢复。" type="info" :closable="false" show-icon style="margin-bottom: 16px;" />

            <!-- 法律文件导入入口 -->
            <el-card shadow="never" style="margin-bottom: 16px;">
              <template #header><b>📜 法律文件导入（law）</b></template>
              <div class="import-row">
                <div class="import-block">
                  <div class="import-title">插入整个文件夹</div>
                  <input ref="lawFolderInputRef" type="file" webkitdirectory multiple hidden @change="onFolderSelected($event, 'law')" />
                  <el-button type="primary" :loading="importingLawFolder" @click="openFolderPicker('law')">选择文件夹导入</el-button>
                  <div class="import-tip">将导入所选文件夹内所有 .pdf / .docx（逐个上传）</div>
                </div>
                <el-divider direction="vertical" />
                <div class="import-block">
                  <div class="import-title">插入单个文件</div>
                  <el-upload :auto-upload="false" :show-file-list="false" accept=".pdf,.docx" :on-change="(f)=>handleFilePick(f,'law')">
                    <el-button :loading="uploadingLaw" :disabled="!!selectedLawFile">{{ selectedLawFile ? selectedLawFile.name : '选择文件' }}</el-button>
                  </el-upload>
                  <el-button v-if="selectedLawFile" type="primary" style="margin-top:8px;" :loading="uploadingLaw" @click="importSingleFile('law')">上传并导入</el-button>
                  <div class="import-tip" v-if="selectedLawFile">已选择：{{ selectedLawFile.name }}</div>
                </div>
              </div>
            </el-card>

            <!-- 法律案例导入入口 -->
            <el-card shadow="never" style="margin-bottom: 16px;">
              <template #header><b>📋 法律案例导入（sample）</b></template>
              <div class="import-row">
                <div class="import-block">
                  <div class="import-title">插入整个文件夹</div>
                  <input ref="sampleFolderInputRef" type="file" webkitdirectory multiple hidden @change="onFolderSelected($event, 'sample')" />
                  <el-button type="primary" :loading="importingSampleFolder" @click="openFolderPicker('sample')">选择文件夹导入</el-button>
                  <div class="import-tip">将导入所选文件夹内所有 .pdf / .docx（逐个上传）</div>
                </div>
                <el-divider direction="vertical" />
                <div class="import-block">
                  <div class="import-title">插入单个文件</div>
                  <el-upload :auto-upload="false" :show-file-list="false" accept=".pdf,.docx" :on-change="(f)=>handleFilePick(f,'sample')">
                    <el-button :loading="uploadingSample" :disabled="!!selectedSampleFile">{{ selectedSampleFile ? selectedSampleFile.name : '选择文件' }}</el-button>
                  </el-upload>
                  <el-button v-if="selectedSampleFile" type="primary" style="margin-top:8px;" :loading="uploadingSample" @click="importSingleFile('sample')">上传并导入</el-button>
                  <div class="import-tip" v-if="selectedSampleFile">已选择：{{ selectedSampleFile.name }}</div>
                </div>
              </div>
            </el-card>

            <!-- 本账号已保存的导入路径 -->
            <el-card shadow="never" style="margin-bottom: 16px;">
              <template #header>
                <div style="display:flex; align-items:center; gap:12px;">
                  <b>👤 我的已导入数据源</b>
                  <el-button size="small" :loading="reloading" @click="reloadMyData">重新导入我的数据</el-button>
                </div>
              </template>
              <el-empty v-if="myImports.length === 0" description="暂无已保存的导入路径" :image-size="60" />
              <el-table v-else :data="myImports" size="small" border stripe>
                <el-table-column prop="source_type" label="类型" width="90">
                  <template #default="{ row }">
                    <el-tag :type="row.source_type === 'law' ? 'danger' : 'success'" size="small">{{ row.source_type === 'law' ? '法律' : '案例' }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="kind" label="方式" width="80">
                  <template #default="{ row }">{{ row.kind === 'folder' ? '目录' : '文件' }}</template>
                </el-table-column>
                <el-table-column prop="path" label="目录 / 文件地址" />
                <el-table-column prop="created_at" label="记录时间" width="180" />
              </el-table>
            </el-card>
          </div>
        </el-tab-pane>

        <!-- Tab 4: 管理员（仅 admin 账号可见） -->
        <el-tab-pane v-if="isAdmin" label="🔐 管理" name="admin">
          <div class="manage-panel">
            <el-divider content-position="left">删除用户数据</el-divider>
            <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
              <el-input
                v-model="adminDeleteTarget"
                placeholder="输入要删除的用户名 或 用户ID"
                style="max-width: 320px;"
                clearable
                @keyup.enter="adminDeleteUser"
              />
              <el-button type="danger" :loading="adminDeleting" @click="adminDeleteUser">
                删除该用户全部数据
              </el-button>
            </div>

            <el-divider content-position="left">数据库所有表数据</el-divider>
            <div style="margin-bottom:12px;">
              <el-button size="small" :loading="adminLoading" @click="loadAdminTables">刷新表数据</el-button>
            </div>
            <div v-for="t in adminTables" :key="t.name" style="margin-bottom:20px;">
              <div style="display:flex; align-items:center; gap:10px;">
                <b style="color:#e0e7ff;">表：{{ t.name }}</b>
                <span style="font-size:12px; color:#909399;">
                  （{{ t.rows ? t.rows.length : 0 }} 行，主键：{{ t.pk }}{{ t.error ? '，查询出错：' + t.error : '' }}）
                </span>
              </div>
              <el-table v-if="t.rows && t.rows.length" :data="t.rows" size="small" border stripe style="margin-top:8px;" max-height="320">
                <el-table-column
                  v-for="(v, k) in t.rows[0]"
                  :key="k"
                  :prop="k"
                  :label="k"
                  min-width="120"
                  show-overflow-tooltip
                />
                <el-table-column label="操作" width="90" fixed="right">
                  <template #default="{ row }">
                    <el-button
                      size="small"
                      type="danger"
                      link
                      @click="adminDeleteRow(t, row)"
                    >删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-else-if="!t.error" description="无数据" :image-size="40" style="padding:8px 0;" />
            </div>
            <el-empty v-if="!adminLoading && adminTables.length === 0" description="暂无数据，点击「刷新表数据」加载" />
          </div>
        </el-tab-pane>
      </el-tabs>
    </main>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import Login from './views/Login.vue'
import Register from './views/Register.vue'
import './styles/theme.css'

// 导入法律文件（数百条条文 embedding）可能耗时数十秒，超时放宽到 5 分钟；
// 聊天走原生 fetch（/api/chat/stream），不受此 axios 实例影响。
const api = axios.create({ baseURL: '/api', timeout: 300000 })

// 登录状态管理
const isLoggedIn = ref(!!localStorage.getItem('token'))
const username = ref(localStorage.getItem('username') || '')
const authVisible = ref(false)
const authMode = ref('login')  // 'login' | 'register'

function showAuth(mode) {
  authMode.value = mode
  authVisible.value = true
}

function onLoginSuccess(data) {
  isLoggedIn.value = true
  username.value = data.username
  userId.value = Number(data.userId) || Number(localStorage.getItem('user_id')) || 0
  isAdmin.value = !!data.isAdmin
  authVisible.value = false
  if (isAdmin.value) {
    // 管理员登录后直接进入管理页
    activeTab.value = 'admin'
    loadAdminTables()
  } else {
    // 加载该用户绑定的 LLM 配置
    loadLlmConfig(userId.value)
    // 登录后自动恢复该用户已保存的导入路径数据（已导入过的文件会自动跳过）
    // reloadMyData 内部完成后会统一刷新知识库文件列表，避免"先0条后正确"的闪烁
    reloadMyData()
    // 启动监控指标自动刷新
    fetchMetrics()
    if (metricsTimer) clearInterval(metricsTimer)
    metricsTimer = setInterval(fetchMetrics, 5000)
  }
}

function onRegisterSuccess() {
  // 注册成功，切换到登录
  authMode.value = 'login'
}

function logout() {
  localStorage.removeItem('token')
  localStorage.removeItem('username')
  localStorage.removeItem('user_id')
  localStorage.removeItem('is_admin')
  isLoggedIn.value = false
  username.value = ''
  userId.value = 0
  isAdmin.value = false
  myImports.value = []
  // 清空 LLM 配置显示，避免跨用户残留
  apiKey.value = ''
  modelName.value = 'qwen-plus'
  baseUrl.value = ''
  llmSaved.value = false
  // 停止监控定时刷新，避免退出后仍轮询
  if (metricsTimer) clearInterval(metricsTimer)
  metricsTimer = null
  metrics.value = null
  circuitStats.value = null
}

// 状态
const activeTab = ref('search')
// 管理员标识（登录时由后端返回，控制管理页展示；刷新时从 localStorage 恢复）
const isAdmin = ref(localStorage.getItem('is_admin') === '1')
// 管理员：数据库所有表数据 / 删除目标输入 / 加载状态
const adminTables = ref([])
const adminLoading = ref(false)
const adminDeleteTarget = ref('')
const adminDeleting = ref(false)
const searchQuery = ref('')
const searchResults = ref([])
const searching = ref(false)
const hasSearched = ref(false)
// 法条分页
const PAGE_SIZE = 20
const searchPage = ref(1)
const pagedResults = computed(() => {
  const start = (searchPage.value - 1) * PAGE_SIZE
  return searchResults.value.slice(start, start + PAGE_SIZE)
})
const chatInput = ref('')
const messages = ref([])
const chatLoading = ref(false)
const chatMessagesRef = ref(null)
// 问答附件（单次对话上下文）
const attachedFile = ref(null)        // 已选文件对象
const chatFileInputRef = ref(null)    // 隐藏的文件 input
const ATTACHMENT_ACCEPT = '.pdf,.docx,.doc,.md,.txt'
// LLM 配置（绑定当前用户，存于 MySQL；登录后从服务器加载）
const apiKey = ref('')
const modelName = ref('qwen-plus')
const baseUrl = ref('')
const llmSaved = ref(false)
const quickQuestions = ['盗窃罪怎么判刑？', '劳动合同解除需要什么条件？', '交通事故责任如何划分？']
const sessionId = ref(sessionStorage.getItem('chat_sid') || '')

// ===== 用户 & 数据导入 =====
const userId = ref(Number(localStorage.getItem('user_id')) || 0)
// 目录导入（浏览器选文件夹，逐个上传）
const lawFolderInputRef = ref(null)
const sampleFolderInputRef = ref(null)
const importingLawFolder = ref(false)
const importingSampleFolder = ref(false)
// 单文件导入（记录 el-upload 选中的文件）
const selectedLawFile = ref(null)
const selectedSampleFile = ref(null)
const uploadingLaw = ref(false)
const uploadingSample = ref(false)
// 我的已存路径
const myImports = ref([])
const reloading = ref(false)
// 知识库中实际已加载的文件列表
const kbFiles = ref([])
const kbTotalFiles = ref(0)
const kbTotalChunks = ref(0)
const loadingKbFiles = ref(false)
const deletingUserData = ref(false)
// 系统运行监控（参考 day64 可观测性）
const metrics = ref(null)
const circuitStats = ref(null)
const loadingMetrics = ref(false)
let metricsTimer = null   // 监控指标自动刷新定时器


async function fetchMetrics() {
  loadingMetrics.value = true
  try {
    const r = await api.get('/metrics')
    metrics.value = r.data.metrics || null
    circuitStats.value = r.data.circuit || null
  } catch (e) {
    // 保持旧值不清空，避免页面刷新闪烁
  } finally { loadingMetrics.value = false }
}

async function handleSearch() {
  if (!searchQuery.value.trim()) return
  hasSearched.value = true
  searching.value = true
  searchPage.value = 1
  try {
    // n_results 调大，一次性取回更多法条用于分页展示
    const res = await api.post('/search', { query: searchQuery.value, n_results: 100, user_id: userId.value })
    searchResults.value = res.data.results
  } catch (e) { searchResults.value = [] }
  finally { searching.value = false }
}

function askQuick(q) { chatInput.value = q; handleChat() }

// 选择问答附件（校验格式与大小）
function onChatFileSelected(event) {
  const file = event.target.files && event.target.files[0]
  if (!file) return
  const ext = '.' + (file.name.split('.').pop() || '').toLowerCase()
  if (!ATTACHMENT_ACCEPT.includes(ext)) {
    ElMessage.warning('仅支持 pdf / word / md / txt 文件')
    event.target.value = ''
    return
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.warning('文件不能超过 10MB')
    event.target.value = ''
    return
  }
  attachedFile.value = file
  event.target.value = ''
}
function removeChatFile() { attachedFile.value = null }
function openChatFilePicker() { chatFileInputRef.value && chatFileInputRef.value.click() }

// ====================== 数据导入 ======================

function handleFilePick(file, type) {
  if (type === 'law') selectedLawFile.value = file.raw || file
  else selectedSampleFile.value = file.raw || file
}

// 打开文件夹选择器
function openFolderPicker(type) {
  const input = type === 'law' ? lawFolderInputRef.value : sampleFolderInputRef.value
  input && input.click()
}

// 浏览器选择文件夹后：收集其中所有 .pdf/.docx，逐个上传导入
async function onFolderSelected(event, type) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  if (!files.length) return
  // 过滤出 pdf/docx（只取文件本身，排除子目录中的同名等）
  const targets = files.filter(f => /\.(pdf|docx)$/i.test(f.name))
  if (!targets.length) { ElMessage.warning('所选文件夹中没有 .pdf 或 .docx 文件'); return }

  const loader = type === 'law' ? importingLawFolder : importingSampleFolder
  loader.value = true
  try {
    // 所有文件塞进同一个 FormData，一次请求批量导入（后端只重建一次索引）
    const fd = new FormData()
    for (const f of targets) fd.append('files', f)
    fd.append('source_type', type)
    fd.append('user_id', String(userId.value))
    const r = await api.post('/import/files', fd)
    const res = r.data.result || {}
    ElMessage.success(`文件夹导入完成：成功 ${res.count || 0} 个文件（${res.chunks || 0} 条），跳过 ${res.skipped || 0} 个，失败 ${(res.errors || []).length} 个`)
    await refreshMyData()
    await fetchKbFiles()
  } catch (e) {
    ElMessage.error(`文件夹导入失败: ${e.response?.data?.detail || e.message}`)
  } finally {
    loader.value = false
  }
}

async function importSingleFile(type) {
  const file = type === 'law' ? selectedLawFile.value : selectedSampleFile.value
  if (!file) { ElMessage.warning('请先选择文件'); return }
  const loader = type === 'law' ? uploadingLaw : uploadingSample
  loader.value = true
  const fd = new FormData()
  fd.append('file', file)
  fd.append('source_type', type)
  fd.append('user_id', String(userId.value))
  try {
    const r = await api.post('/import/file', fd)
    const res = r.data.result || {}
    ElMessage.success(`导入成功 ${res.count} 条，跳过 ${res.skipped}，失败 ${(res.errors || []).length}`)
    if (type === 'law') selectedLawFile.value = null
    else selectedSampleFile.value = null
    await refreshMyData()
    await fetchKbFiles()
  } catch (e) {
    ElMessage.error(`单文件导入失败: ${e.response?.data?.detail || e.message}`)
  } finally { loader.value = false }
}

async function refreshMyData() {
  if (!userId.value) { myImports.value = []; return }
  try {
    const r = await api.post('/import/reload', { path: '', source_type: '', user_id: userId.value })
    myImports.value = r.data.records || []
  } catch (e) { myImports.value = [] }
}

async function reloadMyData() {
  if (!userId.value) { ElMessage.warning('请先登录'); return }
  reloading.value = true
  try {
    const r = await api.post('/import/reload', { path: '', source_type: '', user_id: userId.value })
    const res = r.data.result || {}
    myImports.value = r.data.records || []
    ElMessage.success(`已恢复导入：目录 ${res.folder_count} 个，文件 ${res.file_count} 个，累计入库 ${res.imported_files} 条`)
    await fetchKbFiles()
  } catch (e) {
    ElMessage.error(`数据恢复失败: ${e.response?.data?.detail || e.message}`)
  } finally { reloading.value = false }
}

// 获取当前用户知识库中实际已加载的文件列表
async function fetchKbFiles() {
  if (!userId.value) { kbFiles.value = []; kbTotalFiles.value = 0; kbTotalChunks.value = 0; return }
  loadingKbFiles.value = true
  try {
    const r = await api.post('/kb/files', { path: '', source_type: '', user_id: userId.value })
    kbFiles.value = r.data.files || []
    kbTotalFiles.value = r.data.total_files || 0
    kbTotalChunks.value = r.data.total_chunks || 0
  } catch (e) {
    kbFiles.value = []
    kbTotalFiles.value = 0
    kbTotalChunks.value = 0
  } finally { loadingKbFiles.value = false }
}

// 清空当前用户的本地数据（知识库向量 + 上传文件），需二次确认
async function deleteMyLocalData() {
  if (!userId.value) { ElMessage.warning('请先登录'); return }
  try {
    await ElMessageBox.confirm(
      '确定要清空你的本地知识库数据吗？此操作会删除该账号已导入的法律文件、案例及其向量数据，且不可恢复。',
      '清空本地数据',
      {
        confirmButtonText: '确定清空',
        cancelButtonText: '取消',
        type: 'warning',
        confirmButtonClass: 'danger-confirm-btn',
      }
    )
  } catch (e) { return }  // 用户取消

  deletingUserData.value = true
  try {
    const r = await api.post('/kb/delete', { path: '', source_type: '', user_id: userId.value })
    const res = r.data.result || {}
    ElMessage.success('本地数据已清空')
    // 清空后同步清空前端状态：已导入数据源列表 + 已加载文件列表
    myImports.value = []
    kbFiles.value = []
    kbTotalFiles.value = 0
    kbTotalChunks.value = 0
  } catch (e) {
    ElMessage.error(`清空失败: ${e.response?.data?.detail || e.message}`)
  } finally { deletingUserData.value = false }
}

// ===== 管理员功能 =====

// 查看 MySQL 数据库中所有表的所有数据
async function loadAdminTables() {
  adminLoading.value = true
  try {
    const r = await api.post('/admin/tables', { username: username.value })
    adminTables.value = r.data.tables || []
  } catch (e) {
    ElMessage.error(`查看失败: ${e.response?.data?.detail || e.message}`)
  } finally { adminLoading.value = false }
}

// 删除指定用户名或用户ID的账号及其所有 MySQL 数据
async function adminDeleteUser() {
  const target = adminDeleteTarget.value.trim()
  if (!target) { ElMessage.warning('请输入要删除的用户名或用户ID'); return }
  try {
    await ElMessageBox.confirm(
      `确定要删除用户「${target}」的所有数据库数据吗？此操作会删除该账号、其导入记录和 LLM 配置，且不可恢复。`,
      '删除用户数据',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'danger-confirm-btn' }
    )
  } catch (e) { return }

  adminDeleting.value = true
  try {
    const r = await api.post('/admin/delete_user', { username: username.value, identifier: target })
    ElMessage.success(r.data.message || '删除成功')
    adminDeleteTarget.value = ''
    await loadAdminTables()  // 刷新表数据
  } catch (e) {
    ElMessage.error(`删除失败: ${e.response?.data?.detail || e.message}`)
  } finally { adminDeleting.value = false }
}

// 删除指定表中主键对应的单行数据（user_llm_config 按 user_id，其余按 id）
async function adminDeleteRow(t, row) {
  const pkValue = row[t.pk]
  if (pkValue === undefined || pkValue === null || pkValue === '') {
    ElMessage.warning('无法获取该行主键值')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除表「${t.name}」中 ${t.pk}=${pkValue} 的这一行数据吗？此操作不可恢复。`,
      '删除单行数据',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'danger-confirm-btn' }
    )
  } catch (e) { return }

  try {
    const r = await api.post('/admin/delete_row', {
      username: username.value,
      table: t.name,
      pk_value: String(pkValue)
    })
    ElMessage.success(r.data.message || '删除成功')
    await loadAdminTables()  // 刷新表数据
  } catch (e) {
    ElMessage.error(`删除失败: ${e.response?.data?.detail || e.message}`)
  }
}

async function handleChat() {
  const question = chatInput.value.trim()
  if (!question || chatLoading.value) return
  const file = attachedFile.value
  // 用户消息：附上文件名便于展示
  messages.value.push({ role: 'user', content: file ? `${question}（📎 已附带文件：${file.name}）` : question })
  chatInput.value = ''
  chatLoading.value = true

  // 创建占位助手消息（用 reactive 包裹，后续修改 content 才能触发响应式更新）
  const assistantMsg = reactive({ role: 'assistant', content: '', sources: [], streaming: true })
  messages.value.push(assistantMsg)
  scrollToBottom()

  // 用 fetch + ReadableStream 读取 SSE 流（multipart 表单，支持附件）
  try {
    const fd = new FormData()
    fd.append('question', question)
    fd.append('n_results', '5')
    fd.append('api_key', apiKey.value || '')
    fd.append('model', modelName.value || '')
    fd.append('base_url', baseUrl.value || '')
    fd.append('session_id', sessionId.value)
    fd.append('user_id', String(userId.value))
    if (file) fd.append('file', file)

    const resp = await fetch('/api/chat/stream', {
      method: 'POST',
      body: fd,   // 不要手动设置 Content-Type，浏览器自动带 boundary
    })

    if (!resp.ok || !resp.body) {
      throw new Error(`HTTP ${resp.status}`)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''

    // 逐块解析 SSE 事件
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // SSE 事件之间以空行分隔，逐个处理完整事件
      let sepIdx
      while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
        const rawEvent = buffer.slice(0, sepIdx)
        buffer = buffer.slice(sepIdx + 2)
        const lines = rawEvent.split('\n')
        let eventType = 'message'
        let data = ''
        for (const line of lines) {
          if (line.startsWith('event:')) eventType = line.slice(6).trim()
          else if (line.startsWith('data:')) data += line.slice(5).trim()
        }
        if (!data) continue
        const payload = JSON.parse(data)

        if (eventType === 'META') {
          assistantMsg.sources = payload.sources || []
        } else if (eventType === 'DELTA') {
          assistantMsg.content += payload.delta || ''
          scrollToBottom()
        } else if (eventType === 'DONE') {
          // 保存最终 session_id
          if (payload.session_id) {
            sessionStorage.setItem('chat_sid', payload.session_id)
            sessionId.value = payload.session_id
          }
          assistantMsg.content = payload.answer || assistantMsg.content
        }
      }
    }
  } catch (e) {
    assistantMsg.content = `⚠ 请求失败: ${e.message}`
  } finally {
    assistantMsg.streaming = false
    chatLoading.value = false
    attachedFile.value = null   // 发送完毕清除附件
    scrollToBottom()
  }
}

async function saveLlmConfig() {
  if (!userId.value) { ElMessage.warning('请先登录'); return }
  try {
    await api.post('/llm/config', {
      user_id: userId.value,
      api_key: apiKey.value || '',
      model: modelName.value || '',
      base_url: baseUrl.value || '',
    })
    llmSaved.value = true
    ElMessage.success('LLM 配置已保存到当前账号')
  } catch (e) {
    ElMessage.error(`保存失败: ${e.response?.data?.detail || e.message}`)
  }
}

async function loadLlmConfig(uid) {
  if (!uid) return
  try {
    const r = await api.get('/llm/config', { params: { user_id: uid } })
    apiKey.value = r.data.api_key || ''
    modelName.value = r.data.model || 'qwen-plus'
    baseUrl.value = r.data.base_url || ''
    llmSaved.value = !!r.data.api_key
  } catch (e) { /* 读不到就用默认空值 */ }
}

function parsedAnswer(text) {
  if (!text) return null

  // 识别「法律分析」分隔标记：兼容多种模型输出格式
  //   【法律分析】  |  ## 第二部分：  |  第二部分：
  const markers = [
    '【法律分析】',
    '## 第二部分',
    '## 法律分析',
    '第二部分：',
    '第二部分:',
  ]
  let idx = -1
  for (const m of markers) {
    const i = text.indexOf(m)
    if (i !== -1 && (idx === -1 || i < idx)) idx = i
  }
  if (idx === -1) {
    // 没有可识别的分析分隔，直接整体作为正文（并清理裸露标题）
    return { main: _cleanAnswerHeadings(text), analysis: '' }
  }

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

  // 清理正文中的格式标记（第一部分标题、结论说明行等）
  main = _cleanAnswerHeadings(main)
  // 清理分析段开头的标题标记本身（如 "## 第二部分："、"【法律分析】"）
  analysis = analysis
    .replace(/^#{1,6}\s*第二部分[：:]?/m, '')
    .replace(/^#{1,6}\s*【?法律分析】?[：:]?/m, '')
    .trim()

  return { main: conclusion ? (main + '\n\n' + conclusion) : main, analysis }
}

// 清理回答中裸露的「第一部分/第二部分」等 markdown 标题行
function _cleanAnswerHeadings(s) {
  if (!s) return ''
  return s
    .replace(/^#{1,6}\s*第一部分[：:].*$/m, '')       // 去掉 "## 第一部分：xxx"
    .replace(/^#{1,6}\s*第二部分[：:].*$/m, '')       // 去掉 "## 第二部分：xxx"
    .replace(/^第一部分[：:].*$/m, '')
    .replace(/^第二部分[：:].*$/m, '')
    .replace(/^[－\-·]\s*直接给出答案.*$/m, '')       // 去掉结论说明行
    .replace(/\n*【结论】\s*/g, '')
    .trim()
}

function formatAnswer(text) {
  if (!text) return ''
  return text
    .replace(/&nbsp;/g, ' ')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    // 把 markdown 标题（# / ## / ###）转成加粗，避免裸露的 # 符号
    .replace(/^#{1,6}\s+(.*)$/gm, '<strong>$1</strong>')
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/【引用：(.*?)】/g, '<span class="law-ref">【引用：$1】</span>')
}

function scrollToBottom() {
  nextTick(() => { if (chatMessagesRef.value) chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight })
}

onMounted(() => {
  // 管理员：刷新后恢复进入管理页，并加载数据库表数据
  if (isAdmin.value) {
    activeTab.value = 'admin'
    loadAdminTables()
    return
  }
  // 已登录普通用户：加载其绑定的 LLM 配置 + 恢复其已保存的导入路径数据（已导入文件自动跳过）
  // reloadMyData 完成后内部会统一刷新知识库文件列表
  if (userId.value) {
    loadLlmConfig(userId.value)
    reloadMyData()
    fetchMetrics()   // 加载系统运行监控指标
    // 每 5 秒自动刷新监控指标，让提问后能实时看到统计
    if (metricsTimer) clearInterval(metricsTimer)
    metricsTimer = setInterval(fetchMetrics, 5000)
  }
})

onUnmounted(() => {
  if (metricsTimer) clearInterval(metricsTimer)
})
</script>

