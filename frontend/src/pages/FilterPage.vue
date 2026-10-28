<script setup lang="ts">
// Спам-фильтр и антивирус (только суперадмин): вкладки Сводка / Пороги / Списки / История / Символы.
// Содержимое вкладки монтируется только когда она активна, чтобы не дёргать Rspamd лишними запросами.
import { ref } from 'vue'
import Tabs from 'primevue/tabs'
import TabList from 'primevue/tablist'
import Tab from 'primevue/tab'
import TabPanels from 'primevue/tabpanels'
import TabPanel from 'primevue/tabpanel'
import FilterOverviewTab from '@/pages/filter/FilterOverviewTab.vue'
import FilterActionsTab from '@/pages/filter/FilterActionsTab.vue'
import FilterListsTab from '@/pages/filter/FilterListsTab.vue'
import FilterHistoryTab from '@/pages/filter/FilterHistoryTab.vue'
import FilterSymbolsTab from '@/pages/filter/FilterSymbolsTab.vue'

type TabKey = 'overview' | 'actions' | 'lists' | 'history' | 'symbols'

const tabs: { key: TabKey; label: string; icon: string }[] = [
  { key: 'overview', label: 'Сводка', icon: 'pi pi-chart-bar' },
  { key: 'actions', label: 'Пороги', icon: 'pi pi-sliders-h' },
  { key: 'lists', label: 'Списки', icon: 'pi pi-list-check' },
  { key: 'history', label: 'История', icon: 'pi pi-history' },
  { key: 'symbols', label: 'Символы', icon: 'pi pi-tags' },
]

const active = ref<TabKey>('overview')
</script>

<template>
  <div>
    <h1 class="page-title">Спам-фильтр и антивирус</h1>
    <Tabs :value="active" @update:value="active = $event as TabKey">
      <TabList>
        <Tab v-for="tab in tabs" :key="tab.key" :value="tab.key">
          <i :class="tab.icon" style="margin-right: 0.4rem" />{{ tab.label }}
        </Tab>
      </TabList>
      <TabPanels>
        <TabPanel value="overview"><FilterOverviewTab v-if="active === 'overview'" /></TabPanel>
        <TabPanel value="actions"><FilterActionsTab v-if="active === 'actions'" /></TabPanel>
        <TabPanel value="lists"><FilterListsTab v-if="active === 'lists'" /></TabPanel>
        <TabPanel value="history"><FilterHistoryTab v-if="active === 'history'" /></TabPanel>
        <TabPanel value="symbols"><FilterSymbolsTab v-if="active === 'symbols'" /></TabPanel>
      </TabPanels>
    </Tabs>
  </div>
</template>
