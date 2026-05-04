/**
 * Commit message rules for hallm.
 *
 * - Conventional Commits header (type(scope): subject).
 * - Body: at most 5 non-empty lines.
 *
 * Rules from @commitlint/config-conventional are inlined so the config works
 * with the standalone `brew install commitlint` distribution (which does not
 * bundle the conventional preset). Used by the `commit-msg` pre-commit hook
 * and by opencommit (`OCO_PROMPT_MODULE=@commitlint`).
 */
module.exports = {
  plugins: [
    {
      rules: {
        'body-max-lines': ({ body }) => {
          if (!body) return [true];
          const lines = body.split('\n').filter((line) => line.trim().length > 0);
          return [
            lines.length <= 5,
            `body must not exceed 5 non-empty lines (got ${lines.length})`,
          ];
        },
      },
    },
  ],
  rules: {
    'body-leading-blank': [2, 'always'],
    'body-max-line-length': [2, 'always', 100],
    'body-max-lines': [2, 'always'],
    'footer-leading-blank': [1, 'always'],
    'footer-max-line-length': [2, 'always', 100],
    'header-max-length': [2, 'always', 100],
    'header-trim': [2, 'always'],
    'subject-case': [
      2,
      'never',
      ['sentence-case', 'start-case', 'pascal-case', 'upper-case'],
    ],
    'subject-empty': [2, 'never'],
    'subject-full-stop': [2, 'never', '.'],
    'type-case': [2, 'always', 'lower-case'],
    'type-empty': [2, 'never'],
    'type-enum': [
      2,
      'always',
      [
        'build',
        'chore',
        'ci',
        'docs',
        'feat',
        'fix',
        'perf',
        'refactor',
        'revert',
        'style',
        'test',
      ],
    ],
  },
};
