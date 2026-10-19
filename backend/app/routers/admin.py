from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_session
from ..deps import require_admin
from ..schemas import CouponOut, ReportOut
from ..services import coupon_service, report_service

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.post(
    "/coupons/generate",
    response_model=CouponOut,
    status_code=status.HTTP_201_CREATED,
)
async def generate_coupon(session: AsyncSession = Depends(get_session)):
    """Generate a coupon if an unrewarded order milestone is eligible."""
    coupon = await coupon_service.generate_coupon(session)
    return coupon


@router.get("/report", response_model=ReportOut)
async def report(session: AsyncSession = Depends(get_session)):
    """Read-only reconciliation summary. Repeated calls never mutate state."""
    return await report_service.build_report(session)
