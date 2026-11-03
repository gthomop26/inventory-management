<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="loadError" class="error">{{ loadError }}</div>
    <div v-else>
      <div v-if="confirmation" class="confirmation" role="status">
        <h3 class="confirmation-title">{{ t('restocking.confirmation.title') }}</h3>
        <dl class="confirmation-details">
          <div>
            <dt>{{ t('restocking.confirmation.orderNumber') }}</dt>
            <dd>{{ confirmation.order_number }}</dd>
          </div>
          <div>
            <dt>{{ t('restocking.confirmation.leadTime') }}</dt>
            <dd>{{ t('restocking.confirmation.days', { count: confirmation.lead_time_days }) }}</dd>
          </div>
          <div>
            <dt>{{ t('restocking.confirmation.expectedDelivery') }}</dt>
            <dd>{{ formatDate(confirmation.expected_delivery) }}</dd>
          </div>
          <div>
            <dt>{{ t('restocking.confirmation.total') }}</dt>
            <dd>{{ formatCurrency(confirmation.total_value, currentCurrency) }}</dd>
          </div>
        </dl>
        <router-link to="/orders" class="confirmation-link">
          {{ t('restocking.confirmation.viewOrders') }}
        </router-link>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budget') }}</h3>
        </div>
        <input
          class="budget-slider"
          type="range"
          min="0"
          :max="sliderMax"
          step="1000"
          :value="budget"
          :aria-label="t('restocking.budgetSlider')"
          :disabled="sliderMax === 0"
          @input="onBudgetInput"
        />
        <div class="budget-summary">
          <div class="budget-stat">
            <div class="stat-label">{{ t('restocking.budget') }}</div>
            <div class="budget-value">{{ formatCurrency(budget, currentCurrency) }}</div>
          </div>
          <div class="budget-stat">
            <div class="stat-label">{{ t('restocking.allocated') }}</div>
            <div :class="['budget-value', { over: isOverBudget }]">{{ formatCurrency(allocated, currentCurrency) }}</div>
          </div>
          <div class="budget-stat">
            <div class="stat-label">{{ t('restocking.remaining') }}</div>
            <div :class="['budget-value', { over: isOverBudget }]">{{ formatCurrency(remaining, currentCurrency) }}</div>
          </div>
        </div>
        <div v-if="isOverBudget" class="error over-budget" role="alert">
          {{ t('restocking.overBudget', { amount: formatCurrency(-remaining, currentCurrency) }) }}
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }} ({{ rows.length }})</h3>
        </div>
        <div v-if="rows.length === 0" class="loading">{{ t('restocking.noGaps') }}</div>
        <div v-else class="table-container">
          <table>
            <thead>
              <tr>
                <th class="col-check">{{ t('restocking.select') }}</th>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.itemName') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th class="num">{{ t('restocking.table.onHand') }}</th>
                <th class="num">{{ t('restocking.table.forecast') }}</th>
                <th class="num">{{ t('restocking.table.gap') }}</th>
                <th class="num">{{ t('restocking.table.unitCost') }}</th>
                <th class="num">{{ t('restocking.table.leadTime') }}</th>
                <th class="num">{{ t('restocking.table.quantity') }}</th>
                <th class="num">{{ t('restocking.table.lineCost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in rows" :key="row.sku" :class="{ 'row-selected': row.selected }">
                <td class="col-check">
                  <input
                    type="checkbox"
                    :checked="row.selected"
                    :aria-label="t('restocking.select') + ' ' + row.sku"
                    @change="setSelected(row.sku, $event.target.checked)"
                  />
                </td>
                <td><strong>{{ row.sku }}</strong></td>
                <td>{{ translateProductName(row.name) }}</td>
                <td>
                  <span :class="['badge', row.trend]">{{ t(`trends.${row.trend}`) }}</span>
                </td>
                <td class="num">{{ row.onHand.toLocaleString() }}</td>
                <td class="num">{{ row.forecast.toLocaleString() }}</td>
                <td class="num">{{ row.gap.toLocaleString() }}</td>
                <td class="num">{{ formatCurrency(row.unitCost, currentCurrency) }}</td>
                <td class="num">{{ row.leadTime }}</td>
                <td class="num">
                  <input
                    class="qty-input"
                    type="number"
                    min="1"
                    step="1"
                    :value="row.quantity"
                    :aria-label="t('restocking.table.quantity') + ' ' + row.sku"
                    @input="setQuantity(row.sku, $event.target.value)"
                  />
                </td>
                <td class="num">{{ formatCurrency(row.quantity * row.unitCost, currentCurrency) }}</td>
              </tr>
            </tbody>
          </table>
        </div>

        <div class="order-footer">
          <div class="order-summary">
            <span>{{ t('restocking.selectedCount', { count: selectedItems.length }) }}</span>
            <strong>{{ formatCurrency(allocated, currentCurrency) }}</strong>
          </div>
          <button
            type="button"
            class="place-order"
            :disabled="selectedItems.length === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.submitting') : t('restocking.placeOrder') }}
          </button>
        </div>
        <div v-if="submitError" class="error" role="alert">{{ submitError }}</div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'

// Lower rank = higher priority
const TREND_RANK = { increasing: 0, stable: 1, decreasing: 2 }

export default {
  name: 'Restocking',
  setup() {
    const { t, currentLocale, currentCurrency, translateProductName } = useI18n()

    const loading = ref(true)
    const loadError = ref(null)
    const submitting = ref(false)
    const submitError = ref(null)
    const confirmation = ref(null)

    // Raw data
    const demand = ref([])
    const inventory = ref([])
    const budget = ref(0)
    // Manual edits per SKU: { [sku]: { selected?: boolean, quantity?: number } }.
    // Cleared whenever the slider moves so the recommendation re-flows.
    const overrides = ref({})

    // Items whose forecast exceeds stock, joined with inventory, ranked by priority
    const candidates = computed(() => {
      const bySku = new Map(inventory.value.map(i => [i.sku, i]))
      const list = []
      for (const d of demand.value) {
        const inv = bySku.get(d.item_sku)
        if (!inv) continue
        const gap = Math.ceil(d.forecasted_demand - inv.quantity_on_hand)
        if (!(gap > 0)) continue
        list.push({
          sku: d.item_sku,
          name: d.item_name || inv.name,
          trend: d.trend,
          onHand: inv.quantity_on_hand,
          forecast: d.forecasted_demand,
          gap,
          unitCost: inv.unit_cost,
          leadTime: inv.lead_time_days,
          cost: gap * inv.unit_cost
        })
      }
      // Trend priority first (unknown trends last), then largest gap first
      return list.sort((a, b) => {
        const ra = TREND_RANK[a.trend] ?? 3
        const rb = TREND_RANK[b.trend] ?? 3
        return ra - rb || b.gap - a.gap
      })
    })

    // Slider max: total cost of all gaps rounded up to the next 1000, so the
    // far end of the slider always funds every recommendation.
    const sliderMax = computed(() => {
      const total = candidates.value.reduce((sum, c) => sum + c.cost, 0)
      return Math.ceil(total / 1000) * 1000
    })

    // Greedy fill in priority order: take an item if it fits in the remaining
    // budget, otherwise skip it and keep trying lower-priority (possibly cheaper) items.
    const recommendedSkus = computed(() => {
      const picked = new Set()
      let spent = 0
      for (const c of candidates.value) {
        if (spent + c.cost <= budget.value) {
          picked.add(c.sku)
          spent += c.cost
        }
      }
      return picked
    })

    // Rows = recommendation merged with user overrides
    const rows = computed(() => candidates.value.map(c => {
      const o = overrides.value[c.sku] || {}
      return {
        ...c,
        selected: o.selected ?? recommendedSkus.value.has(c.sku),
        quantity: o.quantity ?? c.gap
      }
    }))

    // Selected rows with a valid quantity are what will actually be ordered
    const selectedItems = computed(() => rows.value.filter(r => r.selected && r.quantity > 0))

    const allocated = computed(() =>
      selectedItems.value.reduce((sum, r) => sum + r.quantity * r.unitCost, 0))
    const remaining = computed(() => budget.value - allocated.value)
    const isOverBudget = computed(() => allocated.value > budget.value)

    const onBudgetInput = (event) => {
      budget.value = Number(event.target.value)
      overrides.value = {}
    }

    const setSelected = (sku, selected) => {
      overrides.value = { ...overrides.value, [sku]: { ...overrides.value[sku], selected } }
    }

    const setQuantity = (sku, raw) => {
      const parsed = Math.floor(Number(raw))
      // Empty/invalid input becomes 0, which excludes the row from the order
      const quantity = Number.isFinite(parsed) && parsed > 0 ? parsed : 0
      overrides.value = { ...overrides.value, [sku]: { ...overrides.value[sku], quantity } }
    }

    const loadData = async () => {
      try {
        loading.value = true
        loadError.value = null
        const [d, inv] = await Promise.all([api.getDemandForecasts(), api.getInventory()])
        demand.value = d
        inventory.value = inv
        // Start with every gap funded
        budget.value = sliderMax.value
        overrides.value = {}
      } catch (err) {
        loadError.value = t('restocking.loadError', { message: err.message })
      } finally {
        loading.value = false
      }
    }

    const placeOrder = async () => {
      if (submitting.value || selectedItems.value.length === 0) return
      try {
        submitting.value = true
        submitError.value = null
        confirmation.value = null
        const payload = {
          items: selectedItems.value.map(r => ({ sku: r.sku, quantity: r.quantity }))
        }
        confirmation.value = await api.createRestockOrder(payload)
        overrides.value = {}
      } catch (err) {
        const detail = err.response?.data?.detail
        submitError.value = t('restocking.submitError', {
          message: typeof detail === 'string' ? detail : err.message
        })
      } finally {
        submitting.value = false
      }
    }

    const formatDate = (dateString) => {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return dateString
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      return date.toLocaleDateString(locale, { year: 'numeric', month: 'short', day: 'numeric' })
    }

    onMounted(loadData)

    return {
      t,
      currentCurrency,
      translateProductName,
      formatCurrency,
      formatDate,
      loading,
      loadError,
      submitting,
      submitError,
      confirmation,
      budget,
      sliderMax,
      rows,
      selectedItems,
      allocated,
      remaining,
      isOverBudget,
      onBudgetInput,
      setSelected,
      setQuantity,
      placeOrder
    }
  }
}
</script>

<style scoped>
/* Range input: styled per engine since pseudo-elements cannot be combined in one rule */
.budget-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 6px;
  background: #e2e8f0;
  border-radius: 999px;
  outline: none;
  margin: 0.75rem 0 1.25rem;
  cursor: pointer;
}

.budget-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: #0f172a;
  border: 2px solid #ffffff;
  box-shadow: 0 0 0 1px #64748b;
}

.budget-slider::-moz-range-thumb {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #0f172a;
  border: 2px solid #ffffff;
  box-shadow: 0 0 0 1px #64748b;
}

.budget-slider::-moz-range-track {
  background: #e2e8f0;
  height: 6px;
  border-radius: 999px;
}

.budget-slider:focus-visible::-webkit-slider-thumb {
  box-shadow: 0 0 0 3px #cbd5e1;
}

.budget-slider:focus-visible::-moz-range-thumb {
  box-shadow: 0 0 0 3px #cbd5e1;
}

.budget-slider:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.budget-summary {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1.25rem;
}

.budget-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.budget-value.over {
  color: #dc2626;
}

.over-budget {
  margin-bottom: 0;
}

th.num,
td.num {
  text-align: right;
}

.col-check {
  width: 64px;
  text-align: center;
}

tbody tr.row-selected {
  background: #f8fafc;
}

.qty-input {
  width: 84px;
  padding: 0.25rem 0.5rem;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  color: #0f172a;
  font-size: 0.875rem;
  text-align: right;
}

.qty-input:focus {
  outline: none;
  border-color: #64748b;
}

.order-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid #e2e8f0;
}

.order-summary {
  display: flex;
  gap: 1rem;
  align-items: baseline;
  color: #64748b;
  font-size: 0.938rem;
}

.order-summary strong {
  color: #0f172a;
  font-size: 1.25rem;
}

.place-order {
  background: #0f172a;
  color: #ffffff;
  border: none;
  border-radius: 6px;
  padding: 0.625rem 1.5rem;
  font-size: 0.938rem;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.place-order:hover:not(:disabled) {
  background: #1e293b;
}

.place-order:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.confirmation {
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  border-radius: 10px;
  padding: 1.25rem;
  margin-bottom: 1.25rem;
}

.confirmation-title {
  font-size: 1.125rem;
  font-weight: 700;
  color: #065f46;
  margin-bottom: 0.75rem;
}

.confirmation-details {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.confirmation-details dt {
  color: #64748b;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.confirmation-details dd {
  color: #0f172a;
  font-weight: 600;
}

.confirmation-link {
  color: #2563eb;
  font-weight: 600;
  text-decoration: none;
}

.confirmation-link:hover {
  text-decoration: underline;
}
</style>
