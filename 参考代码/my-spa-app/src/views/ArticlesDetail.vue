<template>
  <div class="article-detail">
    <button class="back-btn" @click="$router.push('/articles')">&larr; 返回列表</button>
    <h1>{{ article.title }}</h1>
    <p class="content">{{ article.content }}</p>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const article = ref({ title: '', content: '' })

function fetchArticle(id) {
  const mockData = {
    "1": { title: 'Vue入门', content: '路由是SPA应用的核心，本文将带你了解Vue Router的基本用法。Vue Router 是 Vue.js 官方的路由管理器，用于构建单页应用（SPA）。通过路由，我们可以在不刷新页面的情况下切换视图组件，实现流畅的用户体验。' },
    "2": { title: 'Axios使用', content: 'Axios是最流行的HTTP库，它基于Promise设计，可以在浏览器和Node.js中使用。Axios提供了拦截器、取消请求、自动转换JSON等强大功能，是Vue项目中发起HTTP请求的首选方案。' }
  }
  article.value = mockData[id] || { title: '404', content: '文章不存在' }
}

onMounted(() => {
  fetchArticle(route.params.id)
})

watch(() => route.params.id, (newId) => fetchArticle(newId))
</script>

