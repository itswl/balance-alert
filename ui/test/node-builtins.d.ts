/**
 * node:test 与 node:assert 的最小声明。
 *
 * 依赖只准装 typescript 和 esbuild，所以不引 @types/node —— 测试里只用到
 * describe / it 和四个断言，手写这十几行比多一个依赖划算。用到新 API 时在这里补。
 */

declare module 'node:test' {
  export function describe(name: string, fn: () => void): void;
  export function it(name: string, fn: () => void | Promise<void>): void;
}

declare module 'node:assert/strict' {
  interface Assert {
    (value: unknown, message?: string): asserts value;
    equal(actual: unknown, expected: unknown, message?: string): void;
    notEqual(actual: unknown, expected: unknown, message?: string): void;
    deepEqual(actual: unknown, expected: unknown, message?: string): void;
    ok(value: unknown, message?: string): asserts value;
    match(value: string, pattern: RegExp, message?: string): void;
    throws(fn: () => unknown, message?: string): void;
  }
  const assert: Assert;
  export default assert;
}
