<template>
  <div class="articles-list">
    <h1>文章列表</h1>
    <div class="article-cards">
      <div v-for="item in articles" :key="item.id" class="article-card" @click="goDetail(item.id)">
        <h3>{{ item.title }}</h3>
        <p>{{ item.summary }}</p>
        <span class="read-more">阅读全文 &rarr;</span>
      </div>
      <p v-if="articles.length === 0" class="empty-tip">暂无文章</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const articles = ref([])

const mockData = [
  {
    id: '1',
    title: 'Vue入门',
    summary: '路由是SPA应用的核心，本文将带你了解Vue Router的基本用法。',
  },
  {
    id: '2',
    title: 'Axios使用',
    summary: 'Axios是最流行的HTTP库，本文介绍如何在Vue中优雅地发起请求。',
  },
]

function fetchArticles() {
  articles.value = mockData
}

function goDetail(id) {
  router.push({ name: 'article-detail', params: { id } })
}

onMounted(() => {
  fetchArticles()
})
</script>

<style scoped>
.article-cards {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.article-card {
  gap: 16px;
  display: flex;
  flex-direction: column;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 18px;
}
</style>
