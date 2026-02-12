'use client';

import Intercom from '@intercom/messenger-js-sdk';

export function IntercomProvider() {
  Intercom({
    app_id: 'v6bxzcb0',
  });

  return <div>Rereflect</div>;
}
