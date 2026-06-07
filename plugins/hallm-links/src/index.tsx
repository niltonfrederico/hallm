import {
  registerRoute,
  registerSidebarEntry,
} from '@kinvolk/headlamp-plugin/lib';
import { K8s } from '@kinvolk/headlamp-plugin/lib';
import {
  Box,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  CircularProgress,
  Grid,
  IconButton,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import React from 'react';

const BUREAU = {
  bg: '#0e0a05',
  panel: '#1a1208',
  gold: '#ffe066',
  goldDim: '#d4af37',
  accent: '#ffd84d',
  border: '#7a5520',
  borderBright: '#a87a30',
  muted: '#b88040',
  text: '#ffb000',
  textBright: '#ffd060',
  stamp: '#c0392b',
  ink: '#0a0703',
} as const;

const MONO =
  '"JetBrains Mono", "Fira Code", "IBM Plex Mono", "Cascadia Code", Menlo, Consolas, monospace';

const SealIcon = ({
  filled,
  size = 22,
}: {
  filled?: boolean;
  size?: number;
}) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
  >
    <circle cx="12" cy="12" r="9.5" />
    <circle cx="12" cy="12" r="7" />
    <path
      d="M12 6.5 13.6 10.4 17.8 10.7 14.6 13.4 15.6 17.5 12 15.3 8.4 17.5 9.4 13.4 6.2 10.7 10.4 10.4 Z"
      fill={filled ? 'currentColor' : 'none'}
    />
  </svg>
);

const BureauEmblem = ({ size = 48 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 64 64" fill="none">
    <circle
      cx="32"
      cy="32"
      r="29"
      stroke={BUREAU.gold}
      strokeWidth="2"
      fill={BUREAU.ink}
    />
    <circle
      cx="32"
      cy="32"
      r="23"
      stroke={BUREAU.goldDim}
      strokeWidth="1"
      fill="none"
    />
    <path
      d="M32 14 L36.2 26.4 L49 26.4 L38.4 34 L42.6 46.4 L32 38.8 L21.4 46.4 L25.6 34 L15 26.4 L27.8 26.4 Z"
      fill={BUREAU.gold}
    />
    <text
      x="32"
      y="58"
      fontFamily={MONO}
      fontSize="6"
      fontWeight="700"
      fill={BUREAU.goldDim}
      textAnchor="middle"
      letterSpacing="1.5"
    >
      ХАЛЛМ
    </text>
  </svg>
);

const BureauHeaderBanner = () => (
  <Box
    sx={{
      border: `2px solid ${BUREAU.gold}`,
      bgcolor: BUREAU.panel,
      px: 3,
      py: 2,
      mb: 3,
      position: 'relative',
      boxShadow: `inset 0 0 0 1px ${BUREAU.ink}, inset 0 0 0 3px ${BUREAU.goldDim}`,
    }}
  >
    <Stack direction="row" alignItems="center" spacing={2}>
      <BureauEmblem size={56} />
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography
          sx={{
            fontFamily: MONO,
            fontWeight: 700,
            letterSpacing: 4,
            color: BUREAU.gold,
            fontSize: 22,
            lineHeight: 1.15,
          }}
        >
          HALLM — SERVICES REGISTRY
        </Typography>
        <Typography
          sx={{
            fontFamily: MONO,
            color: BUREAU.muted,
            fontSize: 11,
            letterSpacing: 3,
            mt: 0.25,
          }}
        >
          РЕЕСТР СЛУЖБ · BUREAU OF COMPUTATIONAL TECHNOLOGY
        </Typography>
      </Box>
      <Box
        sx={{
          fontFamily: MONO,
          fontSize: 10,
          color: BUREAU.goldDim,
          textAlign: 'right',
          letterSpacing: 2,
          flexShrink: 0,
        }}
      >
        <div>ДИРЕКТИВА №</div>
        <div style={{ color: BUREAU.gold, fontSize: 14, fontWeight: 700 }}>
          K3D / HALLM
        </div>
      </Box>
    </Stack>
  </Box>
);

const SectionRule = ({ label }: { label: string }) => (
  <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1.5 }}>
    <Box
      sx={{ flexShrink: 0, color: BUREAU.goldDim, fontFamily: MONO, fontSize: 11 }}
    >
      ▮▮
    </Box>
    <Typography
      sx={{
        fontFamily: MONO,
        color: BUREAU.gold,
        letterSpacing: 4,
        fontWeight: 700,
        fontSize: 12,
        textTransform: 'uppercase',
        flexShrink: 0,
      }}
    >
      {label}
    </Typography>
    <Box
      sx={{
        flex: 1,
        height: '1px',
        bgcolor: BUREAU.border,
        boxShadow: `0 1px 0 ${BUREAU.ink}`,
      }}
    />
  </Stack>
);

const CategoryStamp = ({ category }: { category: string }) => (
  <Box
    sx={{
      display: 'inline-block',
      border: `1px solid ${BUREAU.stamp}`,
      color: BUREAU.stamp,
      px: 0.75,
      py: '1px',
      fontFamily: MONO,
      fontSize: 9,
      fontWeight: 700,
      letterSpacing: 2,
      textTransform: 'uppercase',
      transform: 'rotate(-2deg)',
      lineHeight: 1.4,
    }}
  >
    {category}
  </Box>
);

const ANNOT = 'hallm.local/';
const FAV_STORAGE_KEY = 'hallm-links:favorites';

const sealProps = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

const BUREAU_ICONS: Record<string, React.ReactNode> = {
  gitea: (
    <g {...sealProps}>
      <circle cx="14" cy="14" r="2.6" />
      <circle cx="14" cy="34" r="2.6" />
      <circle cx="34" cy="24" r="2.6" />
      <path d="M14 16.6 L14 31.4" />
      <path d="M16.4 14 Q26 14 28 18 Q30 22 31.4 22.4" />
      <path d="M16.4 34 Q26 34 28 30 Q30 26 31.4 25.6" />
    </g>
  ),
  gotify: (
    <g {...sealProps}>
      <path d="M14 30 L34 30 L31 18 Q24 10 17 18 Z" />
      <path d="M21 33 Q24 36 27 33" />
      <circle cx="24" cy="12" r="1.4" fill="currentColor" stroke="none" />
      <path d="M10 24 L7 22 M10 28 L7 30 M38 24 L41 22 M38 28 L41 30" />
    </g>
  ),
  headlamp: (
    <g {...sealProps}>
      <rect x="11" y="18" width="18" height="12" rx="1" />
      <circle cx="32" cy="24" r="3.4" />
      <path d="M35.4 24 L42 24 M34.5 20.5 L40.5 17 M34.5 27.5 L40.5 31" />
      <path d="M14 30 L14 34 L26 34 L26 30" />
      <path d="M16 18 L16 14 M24 18 L24 14" />
    </g>
  ),
  immich: (
    <g {...sealProps}>
      <path d="M18 14 L20 11 L28 11 L30 14 L36 14 L38 16 L38 35 L10 35 L10 16 L12 14 Z" />
      <circle cx="24" cy="25" r="6.5" />
      <circle cx="24" cy="25" r="2.6" />
      <circle cx="33" cy="18" r="0.9" fill="currentColor" stroke="none" />
    </g>
  ),
  jupyter: (
    <g {...sealProps}>
      <rect x="12" y="9" width="24" height="30" />
      <path d="M16 9 L16 39" />
      <circle cx="14" cy="14" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="14" cy="20" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="14" cy="26" r="0.8" fill="currentColor" stroke="none" />
      <path d="M20 16 L32 16 M20 20 L29 20 M20 24 L32 24 M20 28 L27 28 M20 32 L31 32" />
    </g>
  ),
  minio: (
    <g {...sealProps}>
      <rect x="10" y="11" width="28" height="7" rx="0.5" />
      <rect x="10" y="20.5" width="28" height="7" rx="0.5" />
      <rect x="10" y="30" width="28" height="7" rx="0.5" />
      <circle cx="14" cy="14.5" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="14" cy="24" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="14" cy="33.5" r="0.9" fill="currentColor" stroke="none" />
      <path d="M19 14.5 L33 14.5 M19 24 L33 24 M19 33.5 L33 33.5" />
    </g>
  ),
  'paperless-ngx': (
    <g {...sealProps}>
      <path d="M14 8 L29 8 L34 13 L34 40 L14 40 Z" />
      <path d="M29 8 L29 13 L34 13" />
      <path d="M18 20 L30 20 M18 24 L30 24 M18 28 L30 28 M18 32 L26 32" />
    </g>
  ),
  sure: (
    <g {...sealProps}>
      <circle cx="24" cy="24" r="14" />
      <circle cx="24" cy="24" r="10.5" strokeDasharray="2 2" />
      <path d="M24 14 L24 34" />
      <path d="M29 18 Q24 17.5 21.5 19.5 Q19 21.5 21 23.5 Q23 25.5 27 24.5 Q31 23.5 29 27 Q27 29.5 22 29.5 Q19.5 29.5 18.5 28.5" />
    </g>
  ),
  wallabag: (
    <g {...sealProps}>
      <path d="M8 14 L24 12 L40 14 L40 36 L24 34 L8 36 Z" />
      <path d="M24 12 L24 34" />
      <path d="M12 19 L20 18 M12 23 L20 22 M12 27 L19 26 M28 18 L36 19 M28 22 L36 23 M29 26 L36 27" />
      <path d="M28 12.3 L28 22 L31 19.5 L34 22 L34 12.9" />
    </g>
  ),
};

const ServiceMonogram = ({ title }: { title: string }) => {
  const letters = title
    .replace(/[^A-Za-zА-Яа-я0-9]/g, '')
    .slice(0, 2)
    .toUpperCase();
  return (
    <Box
      sx={{
        color: BUREAU.goldDim,
        fontFamily: MONO,
        fontWeight: 700,
        fontSize: 18,
        letterSpacing: 1,
      }}
    >
      {letters || '—'}
    </Box>
  );
};

const BureauServiceIcon = ({
  iconKey,
  title,
}: {
  iconKey?: string;
  title: string;
}) => {
  const glyph = iconKey ? BUREAU_ICONS[iconKey] : undefined;
  return (
    <Box
      sx={{
        width: 52,
        height: 52,
        flexShrink: 0,
        bgcolor: BUREAU.ink,
        border: `1px solid ${BUREAU.border}`,
        color: BUREAU.gold,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
        '&::before, &::after': {
          content: '""',
          position: 'absolute',
          width: 5,
          height: 5,
          borderColor: BUREAU.goldDim,
          borderStyle: 'solid',
        },
        '&::before': {
          top: 2,
          left: 2,
          borderWidth: '1px 0 0 1px',
        },
        '&::after': {
          bottom: 2,
          right: 2,
          borderWidth: '0 1px 1px 0',
        },
      }}
    >
      {glyph ? (
        <svg width={40} height={40} viewBox="0 0 48 48">
          {glyph}
        </svg>
      ) : (
        <ServiceMonogram title={title} />
      )}
    </Box>
  );
};

type Entry = {
  key: string;
  name: string;
  namespace: string;
  title: string;
  icon?: string;
  category: string;
  description?: string;
  url: string;
};

function extractEntries(ingresses: any[]): Entry[] {
  return ingresses
    .map((ing): Entry | null => {
      const a = ing.metadata?.annotations ?? {};
      if (a[`${ANNOT}dashboard`] !== 'true') return null;

      const tlsHost = ing.spec?.tls?.[0]?.hosts?.[0];
      const ruleHost = ing.spec?.rules?.[0]?.host;
      const host = tlsHost ?? ruleHost;
      if (!host) return null;

      const namespace = ing.metadata.namespace ?? 'default';
      const name = ing.metadata.name;
      return {
        key: `${namespace}/${name}`,
        name,
        namespace,
        title: a[`${ANNOT}title`] ?? name,
        icon: a[`${ANNOT}icon`],
        category: a[`${ANNOT}category`] ?? 'other',
        description: a[`${ANNOT}description`],
        url: `https://${host}`,
      };
    })
    .filter((e): e is Entry => e !== null);
}

function useFavorites(): [Set<string>, (key: string) => void] {
  const [favorites, setFavorites] = React.useState<Set<string>>(() => {
    try {
      const raw = window.localStorage.getItem(FAV_STORAGE_KEY);
      if (!raw) return new Set();
      const parsed = JSON.parse(raw);
      return new Set(Array.isArray(parsed) ? parsed : []);
    } catch {
      return new Set();
    }
  });

  const toggle = React.useCallback((key: string) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      try {
        window.localStorage.setItem(
          FAV_STORAGE_KEY,
          JSON.stringify(Array.from(next)),
        );
      } catch {
        // ignore quota / privacy-mode errors
      }
      return next;
    });
  }, []);

  return [favorites, toggle];
}

function ServiceCard({
  entry,
  isFavorite,
  onToggleFavorite,
}: {
  entry: Entry;
  isFavorite: boolean;
  onToggleFavorite: (key: string) => void;
}) {
  return (
    <Card
      sx={{
        height: '100%',
        position: 'relative',
        bgcolor: BUREAU.panel,
        border: `1px solid ${BUREAU.border}`,
        borderRadius: 0,
        boxShadow: `0 0 0 1px ${BUREAU.ink} inset, 0 2px 0 ${BUREAU.ink}`,
        transition: 'border-color 120ms ease, box-shadow 120ms ease',
        '&:hover': {
          borderColor: BUREAU.gold,
          boxShadow: `0 0 0 1px ${BUREAU.ink} inset, 0 0 0 1px ${BUREAU.goldDim}`,
        },
      }}
    >
      <Tooltip title={isFavorite ? 'снять отметку' : 'отметить'}>
        <IconButton
          size="small"
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onToggleFavorite(entry.key);
          }}
          sx={{
            position: 'absolute',
            top: 4,
            right: 4,
            zIndex: 1,
            color: isFavorite ? BUREAU.gold : BUREAU.border,
            '&:hover': { color: BUREAU.gold, bgcolor: 'transparent' },
          }}
        >
          <SealIcon filled={isFavorite} />
        </IconButton>
      </Tooltip>
      <CardActionArea
        href={entry.url}
        target="_blank"
        rel="noopener noreferrer"
        sx={{
          height: '100%',
          '& .MuiCardActionArea-focusHighlight': {
            bgcolor: BUREAU.gold,
          },
        }}
      >
        <CardContent
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 2,
            height: '100%',
            pr: 5,
          }}
        >
          <BureauServiceIcon iconKey={entry.icon} title={entry.title} />

          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography
              noWrap
              sx={{
                fontFamily: MONO,
                fontWeight: 700,
                color: BUREAU.gold,
                fontSize: 14,
                letterSpacing: 1,
                textTransform: 'uppercase',
              }}
            >
              {entry.title}
            </Typography>
            {entry.description && (
              <Typography
                sx={{
                  fontFamily: MONO,
                  color: BUREAU.text,
                  fontSize: 11,
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                  mt: 0.25,
                }}
              >
                {entry.description}
              </Typography>
            )}
            <Stack
              direction="row"
              alignItems="center"
              spacing={1}
              sx={{ mt: 0.75 }}
            >
              <CategoryStamp category={entry.category} />
              <Typography
                noWrap
                sx={{
                  fontFamily: MONO,
                  color: BUREAU.muted,
                  fontSize: 10,
                  letterSpacing: 1,
                }}
              >
                {entry.url.replace(/^https?:\/\//, '')}
              </Typography>
            </Stack>
          </Box>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}

function Section({
  label,
  entries,
  favorites,
  onToggleFavorite,
}: {
  label: string;
  entries: Entry[];
  favorites: Set<string>;
  onToggleFavorite: (key: string) => void;
}) {
  return (
    <Box sx={{ mb: 4 }}>
      <SectionRule label={label} />
      <Grid container spacing={2}>
        {entries.map((e) => (
          <Grid item xs={12} sm={6} md={4} lg={3} key={e.key}>
            <ServiceCard
              entry={e}
              isFavorite={favorites.has(e.key)}
              onToggleFavorite={onToggleFavorite}
            />
          </Grid>
        ))}
      </Grid>
    </Box>
  );
}

function BureauChip({
  label,
  highlight = false,
  icon,
}: {
  label: string;
  highlight?: boolean;
  icon?: React.ReactNode;
}) {
  return (
    <Stack
      direction="row"
      alignItems="center"
      spacing={0.75}
      sx={{
        border: `1px solid ${highlight ? BUREAU.gold : BUREAU.border}`,
        color: highlight ? BUREAU.gold : BUREAU.muted,
        bgcolor: BUREAU.ink,
        px: 1,
        py: 0.25,
        fontFamily: MONO,
        fontSize: 10,
        letterSpacing: 2,
        textTransform: 'uppercase',
      }}
    >
      {icon}
      <Box component="span">{label}</Box>
    </Stack>
  );
}

function HallmLinksPage() {
  const [ingresses] = K8s.ResourceClasses.Ingress.useList();
  const [favorites, toggleFavorite] = useFavorites();

  if (!ingresses) {
    return (
      <Box sx={{ p: 4, bgcolor: BUREAU.bg, minHeight: '100%' }}>
        <BureauHeaderBanner />
        <Stack alignItems="center" spacing={2} sx={{ mt: 6 }}>
          <CircularProgress
            sx={{ color: BUREAU.gold }}
            size={32}
            thickness={3}
          />
          <Typography
            sx={{
              fontFamily: MONO,
              color: BUREAU.goldDim,
              letterSpacing: 4,
              fontSize: 11,
            }}
          >
            ОБРАБОТКА ЗАПИСЕЙ · LOADING REGISTRY
          </Typography>
        </Stack>
      </Box>
    );
  }

  const raw = ingresses.map((i: any) => i.jsonData ?? i);
  const entries = extractEntries(raw);

  if (entries.length === 0) {
    return (
      <Box sx={{ p: 4, bgcolor: BUREAU.bg, minHeight: '100%' }}>
        <BureauHeaderBanner />
        <Box
          sx={{
            border: `1px dashed ${BUREAU.border}`,
            bgcolor: BUREAU.panel,
            p: 4,
            textAlign: 'center',
          }}
        >
          <Box
            sx={{
              display: 'inline-block',
              border: `2px solid ${BUREAU.stamp}`,
              color: BUREAU.stamp,
              px: 2,
              py: 0.5,
              fontFamily: MONO,
              fontWeight: 700,
              letterSpacing: 4,
              transform: 'rotate(-3deg)',
              mb: 2,
            }}
          >
            НЕТ ЗАПИСЕЙ · NO RECORDS
          </Box>
          <Typography
            sx={{
              fontFamily: MONO,
              color: BUREAU.text,
              fontSize: 12,
              maxWidth: 560,
              mx: 'auto',
              mt: 1,
            }}
          >
            No Ingresses annotated with{' '}
            <Box
              component="code"
              sx={{
                color: BUREAU.gold,
                bgcolor: BUREAU.ink,
                px: 0.5,
                border: `1px solid ${BUREAU.border}`,
              }}
            >
              hallm.local/dashboard: "true"
            </Box>{' '}
            were found. Annotate a service to file it in the registry.
          </Typography>
        </Box>
      </Box>
    );
  }

  const sortByTitle = (a: Entry, b: Entry) => a.title.localeCompare(b.title);

  const favoriteEntries = entries
    .filter((e) => favorites.has(e.key))
    .sort(sortByTitle);

  const grouped = entries.reduce(
    (acc, e) => {
      (acc[e.category] = acc[e.category] || []).push(e);
      return acc;
    },
    {} as Record<string, Entry[]>,
  );

  const sortedCategories = Object.keys(grouped).sort();

  return (
    <Box sx={{ p: 3, bgcolor: BUREAU.bg, minHeight: '100%' }}>
      <BureauHeaderBanner />
      <Stack direction="row" spacing={1} sx={{ mb: 3 }} alignItems="center">
        <BureauChip
          label={`${entries.length} record${entries.length === 1 ? '' : 's'}`}
        />
        {favoriteEntries.length > 0 && (
          <BureauChip
            label={`${favoriteEntries.length} sealed`}
            highlight
            icon={
              <Box
                component="span"
                sx={{
                  display: 'inline-flex',
                  color: BUREAU.gold,
                  mr: 0.25,
                }}
              >
                <SealIcon filled size={12} />
              </Box>
            }
          />
        )}
        <Box sx={{ flex: 1 }} />
        <Typography
          sx={{
            fontFamily: MONO,
            color: BUREAU.muted,
            fontSize: 10,
            letterSpacing: 3,
          }}
        >
          СЛАВА ХАЛЛМ
        </Typography>
      </Stack>
      {favoriteEntries.length > 0 && (
        <Section
          label="Опечатано · Sealed"
          entries={favoriteEntries}
          favorites={favorites}
          onToggleFavorite={toggleFavorite}
        />
      )}
      {sortedCategories.map((cat) => (
        <Section
          key={cat}
          label={cat}
          entries={grouped[cat].sort(sortByTitle)}
          favorites={favorites}
          onToggleFavorite={toggleFavorite}
        />
      ))}
    </Box>
  );
}

registerSidebarEntry({
  parent: null,
  name: 'hallm-links',
  label: 'Registry',
  icon: 'mdi:archive-star',
  url: '/hallm-links',
});

registerRoute({
  path: '/hallm-links',
  sidebar: 'hallm-links',
  name: 'hallm-links',
  exact: true,
  component: HallmLinksPage,
});
