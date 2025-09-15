async def wait_for_all_images_in_viewport(page):
    """确保当前视口中的所有图片完全加载完成"""
    return await page.evaluate("""
    () => {
        return new Promise((resolve) => {
            const checkVisibleImagesLoaded = () => {
                const viewportHeight = window.innerHeight;
                const viewportWidth = window.innerWidth;

                const allImgs = Array.from(document.querySelectorAll('img'));
                const visibleImgs = allImgs.filter(img => {
                    const rect = img.getBoundingClientRect();
                    return (
                        rect.top >= -rect.height &&
                        rect.left >= -rect.width &&
                        rect.bottom <= viewportHeight + rect.height &&
                        rect.right <= viewportWidth + rect.width
                    );
                });

                if (visibleImgs.length === 0) {
                    return resolve('视口中没有图片');
                }

                const allLoaded = visibleImgs.every(img => {
                    return img.complete && img.naturalWidth > 0;
                });

                if (allLoaded) {
                    resolve('视口内所有图片已加载完成');
                } else {
                    setTimeout(checkVisibleImagesLoaded, 200);
                }
            };

            checkVisibleImagesLoaded();
            setTimeout(() => resolve('图片加载超时'), 10000);
        });
    }
    """)


async def scroll_and_load_all_content(page):
    """滚动页面并确保所有内容加载完成"""
    return await page.evaluate("""
    () => {
        return new Promise(async (resolve) => {
            const scrollToBottom = async () => {
                const prevHeight = document.body.scrollHeight;
                window.scrollTo(0, document.body.scrollHeight);

                await new Promise(r => setTimeout(r, 500));

                if (document.body.scrollHeight > prevHeight) {
                    await scrollToBottom();
                }
            };

            await scrollToBottom();

            window.scrollTo(0, 0);

            const viewportHeight = window.innerHeight;
            const totalHeight = document.body.scrollHeight;

            for (let i = 0; i < totalHeight; i += viewportHeight / 2) {
                window.scrollTo(0, i);
                await new Promise(r => setTimeout(r, 200));
            }

            window.scrollTo(0, 0);

            resolve('所有内容已加载');
        });
    }
    """)
