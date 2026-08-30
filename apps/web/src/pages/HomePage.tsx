import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default function HomePage() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>首页</CardTitle>
          <CardDescription>
            基于 Vite + React + TypeScript + shadcn/ui + TailwindCSS 的起始模版
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            此模版已集成：shadcn/ui 组件库、TailwindCSS、React Router、Zustand、
            TanStack Query、Axios、@codeflicker/appwrite SDK。
          </p>
          <Button asChild className="w-full">
            <Link to="/about">前往关于页面 →</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
