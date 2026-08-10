import { expect, test } from '@playwright/test';

test('login and registration entry points render', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByRole('heading', { name: '⚡ 系统' })).toBeVisible();
  await page.getByRole('link', { name: '注册' }).click();
  await expect(page.getByText('创建你的成长账号')).toBeVisible();
  await expect(page.getByPlaceholder('密码（至少10位）')).toBeVisible();
});
