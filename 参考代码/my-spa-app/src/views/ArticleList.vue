<template>
  <div>
    <h2>文章列表</h2>

    <!-- 加载中状态 -->
    <div v-if="loading">⏳ 加载中...</div>

    <!-- 错误状态 -->
    <div v-else-if="error" style="color: red;">
      ❌ 加载失败：{{ error }}
    </div>

    <!-- 数据展示 -->
    <ul v-else>
      <li v-for="post in posts" :key="post.id">
        <strong>{{ post.title }}</strong>
        <p>{{ post.body }}</p>
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

// 定义响应式状态
const posts = ref([])      // 存储文章列表
const loading = ref(false)  // 加载状态
const error = ref(null)     // 错误信息

// 使用 async/await 写法（比 .then 更清晰）
async function fetchPosts() {
  loading.value = true   // 开始加载，显示加载提示
  error.value = null     // 清空之前的错误

  try {
    // await 等待请求完成，response 就是 Axios 的响应对象
    const response = await axios.get('https://jsonplaceholder.typicode.com/posts', {
      params: { _limit: 10 }  // 只获取前10条
    })
    posts.value = response.data  // 将数据存入响应式变量
  } catch (err) {
    // 请求失败时的错误处理
    error.value = err.message
    console.error('请求详情：', err)
  } finally {
    // 无论成功还是失败，都要关闭加载状态
    loading.value = false
  }
}

// 组件挂载时自动加载数据
onMounted(() => {
  fetchPosts()
})
</script>