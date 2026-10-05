"""Server-only durable turn transitions, including messages and demo receipts."""
from fastapi import HTTPException

from ..demo_limits import rpc


def transition_turn(action: str, *, user_id: str, conversation_id: str,
                    request_id: str, question: str, result: dict | None = None) -> dict:
    receipt = rpc('chat_turn', {
        'p_action': action, 'p_user_id': user_id, 'p_conversation_id': conversation_id,
        'p_request_id': request_id, 'p_question': question, 'p_result': result,
    })
    error = receipt.get('error')
    if error == 'conflict':
        raise HTTPException(409, 'This request ID was already used for a different question.')
    if error == 'busy':
        raise HTTPException(409, 'This question is still being processed. Please retry it later.')
    if error == 'not_found':
        raise HTTPException(404, 'Conversation not found.')
    if error == 'quota':
        raise HTTPException(429, 'You have reached the demo allowance of 20 questions per account.')
    if error == 'rate':
        raise HTTPException(429, 'Please wait a minute before asking more questions.',
                            headers={'Retry-After': str(receipt['retry_after'])})
    return receipt
