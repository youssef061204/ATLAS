"""Corrected four-direction body-centre reference conversion, before test scoring."""

from atlas.reference_heading_v7 import cardinal_heading
from calibrate_peachtree_v7 import ORIGIN, SCALE


def body_centers(rows):
    xy = (rows[["Global_X", "Global_Y"]].to_numpy() - ORIGIN) * SCALE
    past = rows.groupby("Vehicle_ID")[["Global_X", "Global_Y"]].diff(10).to_numpy()
    heading = cardinal_heading(rows.Direction.to_numpy(), past)
    return xy - rows.v_length.to_numpy()[:, None] * SCALE * 0.5 * heading
