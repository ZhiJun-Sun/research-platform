// ⚠️ 必须使用 @codeflicker/appwrite，禁止使用官方 appwrite 包
import { Client, Account, Databases, Storage } from '@codeflicker/appwrite'

// endpoint 必须使用 location.origin + '/v1'，禁止硬编码 URL
// project ID 在 .env 中配置：VITE_APPWRITE_PROJECT_ID（不允许含连字符）
const client = new Client()
  .setEndpoint(location.origin + '/v1')
  .setProject(import.meta.env.VITE_APPWRITE_PROJECT_ID ?? '')

export const account = new Account(client)
export const databases = new Databases(client)
export const storage = new Storage(client)

export { client }
