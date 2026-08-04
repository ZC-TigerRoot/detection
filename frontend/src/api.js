import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({
  baseURL: '/api',
  timeout: 180000,
})

http.interceptors.response.use(
  (res) => res,
  (err) => {
    const msg =
      err.response?.data?.detail ||
      err.response?.data?.message ||
      err.message ||
      '请求失败'
    ElMessage.error(typeof msg === 'string' ? msg : JSON.stringify(msg))
    return Promise.reject(err)
  }
)

export const listProjects = (params) => http.get('/projects', { params })
export const getProject = (id) => http.get(`/projects/${id}`)
export const createProject = (data) => http.post('/projects', data)
export const updateProject = (id, data) => http.put(`/projects/${id}`, data)
export const deleteProject = (id) => http.delete(`/projects/${id}`)
export const uploadFiles = (id, files) => {
  const fd = new FormData()
  for (const f of files) fd.append('files', f)
  return http.post(`/projects/${id}/files`, fd)
}
export const parseProject = (id) => http.post(`/projects/${id}/parse`)
export const saveItems = (id, data) => http.put(`/projects/${id}/items`, data)
export const exportProject = (id, data) => http.post(`/projects/${id}/export`, data || {})
export const getFileText = (projectId, fileId) =>
  http.get(`/projects/${projectId}/files/${fileId}/text`)

export function downloadExport(exportId, fileName) {
  const url = `/api/exports/${exportId}/download`
  const a = document.createElement('a')
  a.href = url
  a.download = fileName || 'export.docx'
  a.click()
}

export default http
