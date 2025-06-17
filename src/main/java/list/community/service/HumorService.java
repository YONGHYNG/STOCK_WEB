package list.community.service;

import list.community.dto.HumorPost;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;

import java.util.ArrayList;
import java.util.List;

public class HumorService {

    // 내부에서 URL 받아서 크롤링하는 공통 메서드
    private List<HumorPost> crawl(String url) {
        List<HumorPost> postList = new ArrayList<>();

        try {
            Document doc = Jsoup.connect(url)
                    .userAgent("Mozilla/5.0")
                    .referrer("https://www.google.com")
                    .timeout(10000)
                    .get();

            Elements rows = doc.select("tr.view.list_tr_humordata");

            int count = 0;
            for (Element row : rows) {
                if(count >= 10) break;
                String title = row.select("td.subject").text();
                String hits = row.select("td.hits").text();
                String likes = row.select("td.oknok").text();

                postList.add(new HumorPost(title, hits, likes));
                count++;
            }
        } catch (Exception e) {
            e.printStackTrace();
        }

        return postList;
    }

    // humorbest 게시판 크롤링
    public List<HumorPost> getBestHumorPosts() {
        return crawl("https://www.todayhumor.co.kr/board/list.php?table=humorbest");
    }

    // bestofbest 게시판 크롤링
    public List<HumorPost> getBestOfBestHumorPosts() {
        return crawl("https://www.todayhumor.co.kr/board/list.php?table=bestofbest");
    }
}
