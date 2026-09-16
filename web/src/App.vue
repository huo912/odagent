<template>
  <el-container class="app-container">
    <el-header class="app-header">
      <div class="header-left">
        <el-icon :size="24" color="#409EFF"><Cpu /></el-icon>
        <span class="title">OmniDev Agent 可视化控制台</span>
      </div>
      <div class="header-right">
        <el-tag v-if="overallStatus === 'running'" type="warning" effect="dark">
          运行中
        </el-tag>
        <el-tag
          v-else-if="overallStatus === 'completed'"
          type="success"
          effect="dark"
        >
          已完成
        </el-tag>
        <el-tag
          v-else-if="overallStatus === 'failed'"
          type="danger"
          effect="dark"
        >
          失败
        </el-tag>
        <el-tag v-else type="info" effect="dark">待命</el-tag>
        <span class="total-tokens"
          >总 Token: {{ totalTokens.toLocaleString() }}</span
        >
      </div>
    </el-header>

    <el-main class="app-main">
      <el-row :gutter="16">
        <!-- 左侧：输入与进度 -->
        <el-col :span="10">
          <el-card shadow="never" class="panel">
            <template #header>
              <span>需求输入</span>
            </template>
            <el-upload
              drag
              :auto-upload="false"
              :limit="1"
              accept=".docx,.txt,.md"
              :on-change="onFileChange"
              :on-remove="onFileRemove"
              :file-list="fileList"
            >
              <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
              <div class="el-upload__text">
                拖拽需求文档到此处，或 <em>点击上传</em>
              </div>
              <template #tip>
                <div class="el-upload__tip">支持 .docx / .txt / .md 格式</div>
              </template>
            </el-upload>

            <el-divider content-position="left">或直接输入需求文本</el-divider>

            <el-input
              v-model="requirementText"
              type="textarea"
              :rows="6"
              placeholder="请输入需求描述，例如：开发一个图书管理系统，支持图书增删改查、借阅归还、读者管理……"
            />

            <el-divider content-position="left">执行 Agent 配置</el-divider>

            <div class="agent-select">
              <div class="agent-select-header">
                <span>选择要执行的 Agent</span>
                <el-checkbox
                  v-model="selectAllAgents"
                  :indeterminate="isIndeterminate"
                  @change="onToggleAll"
                >
                  全选
                </el-checkbox>
              </div>
              <el-checkbox-group
                v-model="selectedAgents"
                class="agent-checkbox-group"
              >
                <el-checkbox
                  v-for="opt in agentOptions"
                  :key="opt.value"
                  :value="opt.value"
                  :label="opt.label"
                />
              </el-checkbox-group>
              <div
                v-if="selectedAgents.length === 0"
                class="agent-select-empty"
              >
                请至少选择一个 Agent
              </div>
            </div>

            <div class="action-bar">
              <el-button
                type="primary"
                :loading="running"
                :disabled="
                  running ||
                  (!file && !requirementText.trim()) ||
                  selectedAgents.length === 0
                "
                @click="startRun"
              >
                <el-icon style="margin-right: 4px"><VideoPlay /></el-icon>
                开始生成
              </el-button>
            </div>
          </el-card>

          <el-card shadow="never" class="panel">
            <template #header>
              <span>Agent 进度与 Token</span>
            </template>
            <div v-if="agents.length === 0" class="empty-tip">
              暂无任务，请先输入需求并开始生成
            </div>
            <div v-for="agent in agents" :key="agent.name" class="agent-item">
              <div class="agent-row">
                <span class="agent-name">{{ agent.role || agent.name }}</span>
                <div class="agent-actions">
                  <el-tag size="small" :type="statusType(agent.status)">
                    {{ statusText(agent.status) }}
                  </el-tag>
                  <el-button
                    v-if="agent.status === 'running' && !agent.paused"
                    size="small"
                    type="warning"
                    link
                    :disabled="!running"
                    @click="pauseAgent(agent.name)"
                  >
                    暂停
                  </el-button>
                  <el-button
                    v-if="agent.paused"
                    size="small"
                    type="success"
                    link
                    @click="resumeAgent(agent.name)"
                  >
                    继续
                  </el-button>
                </div>
              </div>
              <el-progress
                :percentage="progressPercent(agent)"
                :status="
                  agent.status === 'failed'
                    ? 'exception'
                    : agent.status === 'completed'
                      ? 'success'
                      : ''
                "
                :stroke-width="8"
              />
              <div class="agent-meta">
                <span v-if="agent.message" class="agent-msg">{{
                  agent.message
                }}</span>
              </div>
            </div>
          </el-card>
        </el-col>

        <!-- 右侧：输出与工程 -->
        <el-col :span="14">
          <el-card shadow="never" class="panel">
            <template #header>
              <span>生成文档</span>
            </template>
            <el-table :data="outputFiles" size="small" empty-text="暂无文档">
              <el-table-column prop="name" label="文档名称" />
              <el-table-column prop="size" label="大小" width="100">
                <template #default="{ row }">{{
                  formatSize(row.size)
                }}</template>
              </el-table-column>
              <el-table-column label="操作" width="120">
                <template #default="{ row }">
                  <el-button
                    size="small"
                    type="primary"
                    link
                    @click="viewOutput(row)"
                  >
                    查看
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <el-card shadow="never" class="panel">
            <template #header>
              <span>落地工程结构</span>
            </template>
            <el-tree
              :data="projectTree"
              :props="{ label: 'name', children: 'children' }"
              node-key="name"
              default-expand-all
              :expand-on-click-node="false"
              @node-click="onTreeNodeClick"
            >
              <template #default="{ data }">
                <span class="tree-node">
                  <el-icon v-if="data.type === 'dir'" color="#E6A23C"
                    ><Folder
                  /></el-icon>
                  <el-icon v-else color="#409EFF"><Document /></el-icon>
                  <span>{{ data.name }}</span>
                </span>
              </template>
            </el-tree>
          </el-card>

          <el-card shadow="never" class="panel">
            <template #header>
              <div class="panel-header">
                <span>MLflow 执行监控</span>
                <el-button
                  size="small"
                  type="primary"
                  link
                  :loading="mlflowLoading"
                  @click="loadMlflowRuns"
                >
                  刷新
                </el-button>
              </div>
            </template>
            <div v-if="mlflowRuns.length === 0" class="empty-tip">
              暂无 MLflow 记录，运行一次任务后即可查看每个 Agent 的 Token 与耗时
            </div>
            <el-table
              v-else
              :data="mlflowRuns"
              size="small"
              empty-text="暂无记录"
            >
              <el-table-column label="Agent" min-width="110">
                <template #default="{ row }">
                  {{ row.params.agent_role || row.name }}
                </template>
              </el-table-column>
              <el-table-column label="状态" width="80">
                <template #default="{ row }">
                  <el-tag
                    size="small"
                    :type="row.status === 'FINISHED' ? 'success' : 'danger'"
                  >
                    {{ row.status }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="Token" width="90">
                <template #default="{ row }">
                  {{ Math.round(row.metrics.total_tokens).toLocaleString() }}
                </template>
              </el-table-column>
              <el-table-column label="耗时(s)" width="80">
                <template #default="{ row }">
                  {{ row.metrics.elapsed.toFixed(1) }}
                </template>
              </el-table-column>
              <el-table-column label="工具调用" width="80">
                <template #default="{ row }">
                  {{ Math.round(row.metrics.tool_calls) }}
                </template>
              </el-table-column>
              <el-table-column label="请求数" width="80">
                <template #default="{ row }">
                  {{ Math.round(row.metrics.successful_requests) }}
                </template>
              </el-table-column>
              <el-table-column label="步骤" width="80">
                <template #default="{ row }">
                  {{ Math.round(row.metrics.current_step) }}/{{
                    Math.round(row.metrics.total_steps)
                  }}
                </template>
              </el-table-column>
              <el-table-column label="时间" width="150">
                <template #default="{ row }">
                  {{ formatTime(row.start_time) }}
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <el-card shadow="never" class="panel">
            <template #header>
              <div class="panel-header">
                <span>记忆系统</span>
                <el-button
                  size="small"
                  type="primary"
                  link
                  :loading="memoryLoading"
                  @click="loadMemories"
                >
                  刷新
                </el-button>
              </div>
            </template>
            <div v-if="memoryList.length === 0" class="empty-tip">
              暂无记忆，Agent 完成任务后会自动积累经验
            </div>
            <el-table
              v-else
              :data="memoryList"
              size="small"
              empty-text="暂无记忆"
            >
              <el-table-column label="Agent" width="130">
                <template #default="{ row }">
                  {{ agentLabel(row.agent) }}
                </template>
              </el-table-column>
              <el-table-column label="Key" width="150">
                <template #default="{ row }">{{ row.key }}</template>
              </el-table-column>
              <el-table-column label="内容" min-width="200">
                <template #default="{ row }">
                  <span class="memory-content">{{ row.content }}</span>
                </template>
              </el-table-column>
              <el-table-column label="时间" width="140">
                <template #default="{ row }">
                  {{ formatTime(row.timestamp * 1000) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="70">
                <template #default="{ row }">
                  <el-button
                    size="small"
                    type="danger"
                    link
                    @click="deleteMemory(row.agent, row.key)"
                  >
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <el-card shadow="never" class="panel">
            <template #header>
              <div class="panel-header">
                <span>检查点</span>
                <el-button
                  size="small"
                  type="primary"
                  link
                  :loading="checkpointLoading"
                  @click="loadCheckpoints"
                >
                  刷新
                </el-button>
              </div>
            </template>
            <div v-if="checkpoints.length === 0" class="empty-tip">
              暂无检查点，任务中断后可基于检查点恢复
            </div>
            <el-table
              v-else
              :data="checkpoints"
              size="small"
              empty-text="暂无检查点"
            >
              <el-table-column label="Run ID" width="110">
                <template #default="{ row }">{{ row.run_id }}</template>
              </el-table-column>
              <el-table-column label="已完成 Agent" min-width="220">
                <template #default="{ row }">
                  <el-tag
                    v-for="c in row.completed"
                    :key="c"
                    size="small"
                    class="cp-tag"
                  >
                    {{ agentLabel(c) }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="更新时间" width="140">
                <template #default="{ row }">
                  {{ formatTime(row.updated_at * 1000) }}
                </template>
              </el-table-column>
              <el-table-column label="操作" width="120">
                <template #default="{ row }">
                  <el-button
                    size="small"
                    type="warning"
                    link
                    @click="resumeFromCheckpoint(row.run_id)"
                  >
                    恢复
                  </el-button>
                  <el-button
                    size="small"
                    type="danger"
                    link
                    @click="deleteCheckpoint(row.run_id)"
                  >
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>
      </el-row>
    </el-main>

    <!-- 文档预览对话框 -->
    <el-dialog
      v-model="previewVisible"
      :title="previewTitle"
      width="70%"
      top="5vh"
    >
      <div class="preview-content">
        <pre>{{ previewContent }}</pre>
      </div>
    </el-dialog>
  </el-container>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from "vue";
import axios from "axios";
import { ElMessage } from "element-plus";

const file = ref(null);
const fileList = ref([]);
const requirementText = ref("");
const running = ref(false);
const overallStatus = ref("pending");
const totalTokens = ref(0);
const agents = ref([]);
const outputFiles = ref([]);
const projectTree = ref([]);
const previewVisible = ref(false);
const previewTitle = ref("");
const previewContent = ref("");

// MLflow 监控数据
const mlflowRuns = ref([]);
const mlflowLoading = ref(false);

// 记忆系统数据
const memoryList = ref([]);
const memoryLoading = ref(false);

// 检查点数据
const checkpoints = ref([]);
const checkpointLoading = ref(false);

// Agent 选择配置
const agentOptions = [
  { value: "requirements_analyst", label: "需求分析师" },
  { value: "software_architect", label: "软件架构师" },
  { value: "database_analyst", label: "数据库架构师" },
  { value: "senior_fullstack_engineer", label: "资深全栈工程师" },
  { value: "senior_software_test_engineer", label: "资深测试工程师" },
];
const selectedAgents = ref(agentOptions.map((o) => o.value));
const selectAllAgents = ref(true);
const isIndeterminate = computed(
  () =>
    selectedAgents.value.length > 0 &&
    selectedAgents.value.length < agentOptions.length,
);

const onToggleAll = (val) => {
  selectedAgents.value = val ? agentOptions.map((o) => o.value) : [];
};

let eventSource = null;

const statusType = (s) =>
  ({
    pending: "info",
    running: "warning",
    paused: "warning",
    completed: "success",
    failed: "danger",
  })[s] || "info";

const statusText = (s) =>
  ({
    pending: "待命",
    running: "运行中",
    paused: "已暂停",
    completed: "已完成",
    failed: "失败",
  })[s] || s;

const progressPercent = (agent) => {
  if (agent.status === "completed") return 100;
  if (agent.status === "failed") return 100;
  if (agent.status === "running" || agent.status === "paused") {
    // 根据已执行步数 / 预估总步数计算进度
    const total = agent.total_steps || 0;
    const current = agent.current_step || 0;
    if (total <= 0) return 0;
    const pct = Math.round((current / total) * 100);
    // 至少显示一点进度，避免看起来卡在 0
    return Math.min(99, Math.max(1, pct));
  }
  return 0;
};

const pauseAgent = async (name) => {
  try {
    const formData = new FormData();
    formData.append("name", name);
    await axios.post("/api/pause", formData);
    ElMessage.info(`已暂停 ${name}`);
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "暂停失败");
  }
};

const resumeAgent = async (name) => {
  try {
    const formData = new FormData();
    formData.append("name", name);
    await axios.post("/api/resume", formData);
    ElMessage.success(`已继续 ${name}`);
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "继续失败");
  }
};

const formatSize = (bytes) => {
  if (!bytes) return "0 B";
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
};

const onFileChange = (uploadFile) => {
  file.value = uploadFile.raw;
  fileList.value = [uploadFile];
};

const onFileRemove = () => {
  file.value = null;
  fileList.value = [];
};

const startRun = async () => {
  const formData = new FormData();
  if (file.value) {
    formData.append("file", file.value);
  } else {
    formData.append("text", requirementText.value);
  }
  formData.append("agents", selectedAgents.value.join(","));
  running.value = true;
  try {
    const res = await axios.post("/api/run", formData);
    ElMessage.success(res.data.message || "任务已启动");
    connectSSE();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "启动失败");
    running.value = false;
  }
};

const connectSSE = () => {
  if (eventSource) eventSource.close();
  eventSource = new EventSource("/api/events");
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      applySnapshot(data);
    } catch (e) {
      // ignore
    }
  };
  eventSource.onerror = () => {
    // 连接断开时尝试重连
  };
};

const applySnapshot = (data) => {
  overallStatus.value = data.overall_status || "pending";
  totalTokens.value = data.total_tokens || 0;
  agents.value = data.agents || [];
  if (data.overall_status === "completed" || data.overall_status === "failed") {
    running.value = false;
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    loadOutputs();
    loadProjectTree();
  }
};

const loadOutputs = async () => {
  try {
    const res = await axios.get("/api/outputs");
    outputFiles.value = res.data.files || [];
  } catch (e) {
    // ignore
  }
};

const loadProjectTree = async () => {
  try {
    const res = await axios.get("/api/project/tree");
    projectTree.value = res.data.tree || [];
    attachPath(projectTree.value);
  } catch (e) {
    // ignore
  }
};

const loadMlflowRuns = async () => {
  mlflowLoading.value = true;
  try {
    const res = await axios.get("/api/mlflow/runs", { params: { limit: 50 } });
    mlflowRuns.value = res.data.runs || [];
  } catch (e) {
    // ignore
  } finally {
    mlflowLoading.value = false;
  }
};

// ---- 记忆系统 ----
const agentLabel = (key) => {
  const map = {
    requirements_analyst: "需求分析师",
    software_architect: "软件架构师",
    database_analyst: "数据库架构师",
    senior_fullstack_engineer: "资深全栈工程师",
    senior_software_test_engineer: "资深测试工程师",
  };
  return map[key] || key;
};

const loadMemories = async () => {
  memoryLoading.value = true;
  try {
    const res = await axios.get("/api/memory");
    const data = res.data.memories || {};
    const list = [];
    Object.keys(data).forEach((agent) => {
      (data[agent] || []).forEach((m) => {
        list.push({
          agent,
          key: m.key,
          content: m.content,
          timestamp: m.timestamp,
        });
      });
    });
    // 按时间倒序
    list.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
    memoryList.value = list;
  } catch (e) {
    // ignore
  } finally {
    memoryLoading.value = false;
  }
};

const deleteMemory = async (agent, key) => {
  try {
    await axios.delete("/api/memory", { params: { agent, key } });
    ElMessage.success("已删除记忆");
    loadMemories();
  } catch (e) {
    ElMessage.error("删除失败");
  }
};

// ---- 检查点 ----
const loadCheckpoints = async () => {
  checkpointLoading.value = true;
  try {
    const res = await axios.get("/api/checkpoints");
    checkpoints.value = res.data.checkpoints || [];
  } catch (e) {
    // ignore
  } finally {
    checkpointLoading.value = false;
  }
};

const resumeFromCheckpoint = async (runId) => {
  try {
    const formData = new FormData();
    formData.append("text", requirementText.value || "恢复上次任务");
    formData.append("agents", selectedAgents.value.join(","));
    formData.append("resume", "true");
    const res = await axios.post("/api/run", formData);
    ElMessage.success(`已从检查点 ${runId} 恢复`);
    running.value = true;
    connectSSE();
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || "恢复失败");
  }
};

const deleteCheckpoint = async (runId) => {
  try {
    await axios.delete(`/api/checkpoints/${runId}`);
    ElMessage.success("已删除检查点");
    loadCheckpoints();
  } catch (e) {
    ElMessage.error("删除失败");
  }
};

const formatTime = (ms) => {
  if (!ms) return "-";
  const d = new Date(ms);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
};

const viewOutput = async (row) => {
  try {
    const res = await axios.get(`/api/outputs/${row.name}`, {
      responseType: "text",
    });
    previewTitle.value = row.name;
    previewContent.value = res.data;
    previewVisible.value = true;
  } catch (e) {
    ElMessage.error("读取文档失败");
  }
};

const onTreeNodeClick = async (data) => {
  if (data.type !== "file") return;
  // 构建路径
  const path = buildPath(data);
  try {
    const res = await axios.get("/api/project/file", {
      params: { path },
      responseType: "text",
    });
    previewTitle.value = path;
    previewContent.value = res.data;
    previewVisible.value = true;
  } catch (e) {
    ElMessage.error("读取文件失败");
  }
};

// 为树节点附加完整路径（在 loadProjectTree 时递归计算）
const attachPath = (nodes, prefix = "") => {
  (nodes || []).forEach((node) => {
    node.fullPath = prefix ? `${prefix}/${node.name}` : node.name;
    if (node.children) attachPath(node.children, node.fullPath);
  });
};

const buildPath = (node) => node.fullPath || node.name;

onMounted(() => {
  loadOutputs();
  loadProjectTree();
  loadMlflowRuns();
  loadMemories();
  loadCheckpoints();
  // 连接 SSE 获取当前状态
  connectSSE();
});

onBeforeUnmount(() => {
  if (eventSource) eventSource.close();
});
</script>

<style scoped>
.app-container {
  min-height: 100vh;
  background: #f0f2f5;
}
.app-header {
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 1px 4px rgba(0, 21, 41, 0.08);
}
.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.title {
  font-size: 18px;
  font-weight: 600;
}
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.total-tokens {
  color: #606266;
  font-size: 14px;
}
.app-main {
  padding: 16px;
}
.panel {
  margin-bottom: 16px;
}
.action-bar {
  margin-top: 12px;
  text-align: right;
}
.agent-select {
  border: 1px solid #ebeef5;
  border-radius: 4px;
  padding: 10px 12px;
  background: #fafafa;
}
.agent-select-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-size: 13px;
  color: #606266;
}
.agent-checkbox-group {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
}
.agent-select-empty {
  color: #f56c6c;
  font-size: 12px;
  margin-top: 6px;
}
.empty-tip {
  color: #909399;
  text-align: center;
  padding: 20px 0;
}
.agent-item {
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}
.agent-item:last-child {
  border-bottom: none;
}
.agent-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.agent-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.agent-name {
  font-weight: 500;
}
.agent-meta {
  display: flex;
  gap: 16px;
  color: #909399;
  font-size: 12px;
  margin-top: 4px;
}
.agent-msg {
  color: #e6a23c;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.tree-node {
  display: flex;
  align-items: center;
  gap: 4px;
}
.preview-content {
  max-height: 70vh;
  overflow: auto;
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 16px;
  border-radius: 4px;
  font-size: 13px;
  line-height: 1.6;
}
.preview-content pre {
  white-space: pre-wrap;
  word-break: break-all;
  font-family: "Consolas", "Courier New", monospace;
}
.memory-content {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  color: #606266;
}
.cp-tag {
  margin-right: 4px;
  margin-bottom: 2px;
}
</style>
