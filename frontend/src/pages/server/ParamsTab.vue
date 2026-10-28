<script setup lang="ts">
// Вкладка «Параметры»: глобальные параметры Postfix/Dovecot из белого списка, сгруппированы по group.
// Каждая строка применяется отдельно (PUT /server/params/{key}); 422 — текст рядом с полем, 502 — Toast.
import { computed, onMounted, reactive, ref } from 'vue'
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Select from 'primevue/select'
import Message from 'primevue/message'
import Tag from 'primevue/tag'
import Skeleton from 'primevue/skeleton'
import * as api from '@/api/server'
import { ApiError } from '@/api/client'
import type { ServerParam } from '@/api/types'
import { useNotify } from '@/composables/useNotify'

const notify = useNotify()

const params = ref<ServerParam[]>([])
const loading = ref(false)
/** Редактируемые значения по ключу (строки; для int — число или null) */
const drafts = reactive<Record<string, string | number | null>>({})
const errors = reactive<Record<string, string | null>>({})
const applying = reactive<Record<string, boolean>>({})

/** Группы в порядке первого появления */
const groups = computed(() => {
  const map = new Map<string, ServerParam[]>()
  for (const p of params.value) {
    const list = map.get(p.group) ?? []
    list.push(p)
    map.set(p.group, list)
  }
  return [...map.entries()].map(([name, items]) => ({ name, items }))
})

function draftFor(p: ServerParam): string | number | null {
  if (p.type === 'int') {
    const n = Number(p.value)
    return Number.isFinite(n) ? n : null
  }
  return p.value
}

function isChanged(p: ServerParam): boolean {
  const d = drafts[p.key]
  if (d === null || d === undefined) return p.value !== ''
  return String(d) !== p.value
}

async function load(): Promise<void> {
  loading.value = true
  try {
    params.value = await api.listServerParams()
    for (const p of params.value) {
      drafts[p.key] = draftFor(p)
      errors[p.key] = null
    }
  } catch (e) {
    notify.error(e, 'Не удалось загрузить параметры')
  } finally {
    loading.value = false
  }
}

async function apply(p: ServerParam): Promise<void> {
  const draft = drafts[p.key]
  const value = draft === null || draft === undefined ? '' : String(draft).trim()
  if (!value) {
    errors[p.key] = 'Значение не может быть пустым'
    return
  }
  applying[p.key] = true
  errors[p.key] = null
  try {
    const saved = await api.updateServerParam(p.key, value)
    const index = params.value.findIndex((x) => x.key === p.key)
    if (index >= 0) params.value[index] = saved
    drafts[p.key] = draftFor(saved)
    notify.success(`${saved.label}: применено (${saved.service} перезагружен)`)
  } catch (e) {
    // 422 — значение не прошло проверку: показываем рядом с полем
    if (e instanceof ApiError && e.status === 422) errors[p.key] = e.message
    else notify.error(e)
  } finally {
    applying[p.key] = false
  }
}

function reset(p: ServerParam): void {
  drafts[p.key] = draftFor(p)
  errors[p.key] = null
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <Message severity="warn" :closable="false" style="margin: 0; flex: 1">
        Значения применяются сразу: после «Применить» соответствующая служба (Postfix или Dovecot) перезагружается.
      </Message>
      <Button label="Обновить" icon="pi pi-refresh" severity="secondary" outlined :loading="loading" @click="load" />
    </div>

    <div v-if="loading && params.length === 0" class="dash-grid" style="margin-top: 0">
      <div v-for="i in 2" :key="i" class="card skeleton-block">
        <Skeleton width="40%" height="1.2rem" />
        <Skeleton v-for="j in 3" :key="j" height="2.2rem" />
      </div>
    </div>

    <div v-else class="params-grid">
      <div v-for="group in groups" :key="group.name" class="card">
        <h2 class="card__title"><i class="pi pi-wrench" /> {{ group.name }}</h2>
        <div class="params">
          <!-- Строка параметра: подпись + тег службы, под ней key, ниже поле на всю ширину и кнопки справа -->
          <div v-for="p in group.items" :key="p.key" class="param">
            <div class="param__head">
              <span class="param__label">{{ p.label }}</span>
              <Tag :value="p.service" severity="secondary" class="param__service" />
            </div>
            <div class="param__key mono">{{ p.key }}</div>
            <div class="param__row">
              <div class="param__field">
                <InputNumber
                  v-if="p.type === 'int'"
                  v-model="(drafts[p.key] as number | null)"
                  :min="p.min"
                  :max="p.max"
                  :use-grouping="false"
                  :invalid="!!errors[p.key]"
                  fluid
                />
                <Select
                  v-else-if="p.type === 'enum'"
                  v-model="(drafts[p.key] as string | null)"
                  :options="p.values ?? []"
                  :invalid="!!errors[p.key]"
                  fluid
                />
                <InputText v-else v-model="(drafts[p.key] as string | null)" :invalid="!!errors[p.key]" fluid />
              </div>
              <div class="param__actions">
                <Button v-tooltip.top="'Вернуть текущее'" icon="pi pi-undo" text rounded size="small" severity="secondary" aria-label="Вернуть текущее" :disabled="!isChanged(p)" @click="reset(p)" />
                <Button label="Применить" size="small" :loading="applying[p.key]" :disabled="!isChanged(p)" @click="apply(p)" />
              </div>
            </div>
            <div v-if="p.type === 'int' && (p.min !== undefined || p.max !== undefined)" class="form__hint">
              диапазон {{ p.min ?? '…' }} – {{ p.max ?? '…' }}
            </div>
            <div v-if="errors[p.key]" class="form__hint" style="color: var(--p-red-500)">{{ errors[p.key] }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Сетка карточек групп: от 460px, на узких экранах одна колонка; ничего не выходит за границы карточки */
.params-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(460px, 100%), 1fr));
  gap: 1rem;
}

.params-grid > .card {
  min-width: 0;
}

.params {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}

.param {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
  min-width: 0;
  padding-bottom: 0.9rem;
  border-bottom: 1px solid var(--app-card-border);
}

.param:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.param__head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 0.5rem;
  min-width: 0;
}

.param__label {
  font-weight: 500;
}

.param__service {
  font-size: 0.7rem;
}

.param__key {
  font-size: 0.78rem;
  color: var(--p-text-muted-color);
  overflow-wrap: anywhere;
}

.param__row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.param__field {
  flex: 1 1 auto;
  min-width: 0;
}

.param__field :deep(.p-inputtext),
.param__field :deep(.p-inputnumber),
.param__field :deep(.p-select) {
  width: 100%;
}

.param__actions {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 0.25rem;
  white-space: nowrap;
}
</style>
