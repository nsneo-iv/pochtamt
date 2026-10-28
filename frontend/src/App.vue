<script setup lang="ts">
// Корневой компонент: глобальные Toast и ConfirmDialog + текущий маршрут
import Toast from 'primevue/toast'
import ConfirmDialog from 'primevue/confirmdialog'
</script>

<template>
  <Toast position="top-right" />
  <ConfirmDialog />
  <RouterView />
</template>
