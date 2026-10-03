/**
 * ProvenanceChip: whether a proposed product is known or a guess (H15).
 */

import React from 'react'
import { render, screen } from '@testing-library/react'
import { ProvenanceChip } from '../ProvenanceChip'

beforeEach(() => {
  window.localStorage.clear()
})

describe('ProvenanceChip', () => {
  it('shows nothing for a line with no source', () => {
    const { container } = render(<ProvenanceChip source={null} verified={false} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows nothing for a source of none', () => {
    const { container } = render(<ProvenanceChip source="none" verified={false} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows known for a verified mapping', () => {
    render(<ProvenanceChip source="alias" verified={true} />)
    expect(screen.getByText('known')).toBeInTheDocument()
  })

  it('shows auto for a proposal', () => {
    render(<ProvenanceChip source="selected" verified={false} />)
    expect(screen.getByText('auto')).toBeInTheDocument()
  })

  describe('display language (Post-MVP frontier item 13, phase 3)', () => {
    it('shows the Finnish words once the cook has chosen Suomi', () => {
      window.localStorage.setItem('kyokki.language', 'fi')
      render(<ProvenanceChip source="alias" verified={true} />)
      expect(screen.getByText('tiedossa')).toBeInTheDocument()
    })

    it('shows the Finnish auto word for a proposal', () => {
      window.localStorage.setItem('kyokki.language', 'fi')
      render(<ProvenanceChip source="selected" verified={false} />)
      expect(screen.getByText('arvio')).toBeInTheDocument()
    })
  })
})
