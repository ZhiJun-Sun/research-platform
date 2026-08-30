import { Link } from 'react-router'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>关于</CardTitle>
          <CardDescription>关于本项目的说明</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            本模版由 CodeFlicker  skill 生成，
            集成了快手内部全栈开发所需的基础设施。
          </p>
          <Button asChild variant="outline" className="w-full">
            <Link to="/">← 返回首页</Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
