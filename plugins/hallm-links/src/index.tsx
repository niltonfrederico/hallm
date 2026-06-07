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

const StarIcon = (props: { filled?: boolean }) => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
    {props.filled ? (
      <path d="M12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z" />
    ) : (
      <path d="M22 9.24l-7.19-.62L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.63-7.03zM12 15.4l-3.76 2.27 1-4.28-3.32-2.88 4.38-.38L12 6.1l1.71 4.04 4.38.38-3.32 2.88 1 4.28z" />
    )}
  </svg>
);

const ANNOT = 'hallm.local/';
const ICON_CDN = 'https://cdn.jsdelivr.net/gh/walkxcode/dashboard-icons/png';
const FAV_STORAGE_KEY = 'hallm-links:favorites';

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
    <Card sx={{ height: '100%', position: 'relative' }}>
      <Tooltip title={isFavorite ? 'Unfavorite' : 'Favorite'}>
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
            color: isFavorite ? 'warning.main' : 'text.disabled',
          }}
        >
          <StarIcon filled={isFavorite} />
        </IconButton>
      </Tooltip>
      <CardActionArea
        href={entry.url}
        target="_blank"
        rel="noopener noreferrer"
        sx={{ height: '100%' }}
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
          {entry.icon && (
            <img
              src={`${ICON_CDN}/${entry.icon}.png`}
              alt={entry.title}
              width={48}
              height={48}
              style={{ objectFit: 'contain', flexShrink: 0 }}
              onError={(e) => {
                (e.currentTarget as HTMLImageElement).style.display = 'none';
              }}
            />
          )}
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="subtitle1" noWrap>
              {entry.title}
            </Typography>
            {entry.description && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                  overflow: 'hidden',
                }}
              >
                {entry.description}
              </Typography>
            )}
            <Typography
              variant="caption"
              color="text.disabled"
              sx={{ display: 'block', mt: 0.5 }}
            >
              {entry.url.replace(/^https?:\/\//, '')}
            </Typography>
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
      <Typography
        variant="overline"
        color="text.secondary"
        sx={{ display: 'block', mb: 1 }}
      >
        {label}
      </Typography>
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

function HallmLinksPage() {
  const [ingresses] = K8s.ResourceClasses.Ingress.useList();
  const [favorites, toggleFavorite] = useFavorites();

  if (!ingresses) {
    return (
      <Box sx={{ p: 4, display: 'flex', justifyContent: 'center' }}>
        <CircularProgress />
      </Box>
    );
  }

  const raw = ingresses.map((i: any) => i.jsonData ?? i);
  const entries = extractEntries(raw);

  if (entries.length === 0) {
    return (
      <Box sx={{ p: 4 }}>
        <Typography variant="h5">Hallm Services</Typography>
        <Typography color="text.secondary" sx={{ mt: 2 }}>
          No Ingresses annotated with <code>hallm.local/dashboard: "true"</code>{' '}
          were found. Add the annotation to make a service show up here.
        </Typography>
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
    <Box sx={{ p: 3 }}>
      <Stack
        direction="row"
        alignItems="baseline"
        spacing={2}
        sx={{ mb: 3 }}
      >
        <Typography variant="h4">Hallm Services</Typography>
        <Chip
          label={`${entries.length} service${entries.length === 1 ? '' : 's'}`}
          size="small"
        />
        {favoriteEntries.length > 0 && (
          <Chip
            icon={<StarIcon />}
            label={`${favoriteEntries.length} favorite${favoriteEntries.length === 1 ? '' : 's'}`}
            size="small"
            color="warning"
            variant="outlined"
          />
        )}
      </Stack>
      {favoriteEntries.length > 0 && (
        <Section
          label="★ Favorites"
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
  label: 'Hallm Services',
  icon: 'mdi:view-dashboard-variant',
  url: '/hallm-links',
});

registerRoute({
  path: '/hallm-links',
  sidebar: 'hallm-links',
  name: 'hallm-links',
  exact: true,
  component: HallmLinksPage,
});
