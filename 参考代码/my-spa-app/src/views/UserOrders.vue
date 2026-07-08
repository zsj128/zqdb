<template>
  <div class="orders-page">
    <h3>我的订单</h3>
    <table class="order-table">
      <thead>
        <tr>
          <th>订单号</th>
          <th>商品</th>
          <th>状态</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(o, i) in orders" :key="i">
          <td>{{ o.id }}</td>
          <td>{{ o.item }}</td>
          <td><span :class="'status-' + o.status.toLowerCase()">{{ o.status }}</span></td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
const orders = [
  { id: '#1001', item: 'Vue高级教程', status: '已完成' },
  { id: '#1002', item: 'TypeScript入门', status: '进行中' },
]
</script>