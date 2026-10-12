import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "履历校准台 | Resume Job Matcher",
  description: "基于真实简历事实的岗位匹配与简历优化工具"
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
