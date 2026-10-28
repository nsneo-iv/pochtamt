<script setup lang="ts">
// Переключатель темы: светлая / тёмная / как в системе
import SelectButton from 'primevue/selectbutton'
import { useThemeStore } from '@/stores/theme'
import type { ThemeMode } from '@/stores/theme'

const theme = useThemeStore()

const options: { value: ThemeMode; icon: string; title: string }[] = [
  { value: 'light', icon: 'pi pi-sun', title: 'Светлая тема' },
  { value: 'dark', icon: 'pi pi-moon', title: 'Тёмная тема' },
  { value: 'system', icon: 'pi pi-desktop', title: 'Как в системе' },
]
</script>

<template>
  <SelectButton
    :model-value="theme.mode"
    :options="options"
    option-value="value"
    :allow-empty="false"
    size="small"
    aria-label="Тема оформления"
    @update:model-value="theme.setMode($event)"
  >
    <template #option="{ option }">
      <i :class="option.icon" :title="option.title" :aria-label="option.title" />
    </template>
  </SelectButton>
</template>
